"""
ei_pipeline.py  --  Edge Impulse training pipeline for AnimalRaw (Syntiant NDP120 path)
Converts monkey sounds, uploads to Edge Impulse, trains with Syntiant DSP, downloads .synpkg.

Deployment target: Syntiant NDP120 via Arduino Nicla Voice (syntiant-nicla-ndp120)
Classes: monkey (positive) + z_openset (negative catch-all, must be alphabetically last)

Usage:
  python src/ei_pipeline.py prep       # convert + split local audio to 1-second clips
  python src/ei_pipeline.py clear      # delete all samples from EI project (wipes tutorial data)
  python src/ei_pipeline.py upload     # upload clips to EI project (noise+unknown → z_openset)
  python src/ei_pipeline.py impulse    # verify/update impulse to use Syntiant DSP block
  python src/ei_pipeline.py train      # generate features + start training
  python src/ei_pipeline.py status     # check training job status
  python src/ei_pipeline.py download   # download finished syntiant-nicla-ndp120 deployment
  python src/ei_pipeline.py info       # print project info and sample counts
  python src/ei_pipeline.py all        # clear → upload → impulse → train → wait → download
"""

import os, sys, json, time, shutil, zipfile, subprocess
import requests
from pathlib import Path

# ── Config ─────────────────────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent.parent

def _load_dotenv(path: Path):
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]

        if key and key not in os.environ:
            os.environ[key] = value

_load_dotenv(PROJECT_ROOT / ".env")

INGEST_KEY = os.environ.get("EI_API_KEY")
ADMIN_KEY  = os.environ.get("EI_API_KEY")
API_KEY    = ADMIN_KEY

PROJECT_ID = 975711   # cloned Syntiant-RC-Go-Stop-NDP120 project

STUDIO_URL = "https://studio.edgeimpulse.com/v1/api"
INGEST_URL = "https://ingestion.edgeimpulse.com/api"

MONKEY_DIR   = PROJECT_ROOT / "momkeysounds"
CLIPS_DIR    = PROJECT_ROOT / "audio_clips"
DEPLOY_DIR   = PROJECT_ROOT / "deployment"

SAMPLE_RATE = 16000
CLIP_MS     = 1000
STRIDE_MS   = 500

# Syntiant class names — negative class must be alphabetically LAST
CLASS_POSITIVE = "monkey"
CLASS_NEGATIVE = "z_openset"   # catch-all for noise, unknown, anything else

# Local label dirs → EI upload label mapping
LABEL_MAP = {
    "monkey":  CLASS_POSITIVE,
    "noise":   CLASS_NEGATIVE,
    "unknown": CLASS_NEGATIVE,
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _check_project_id():
    if not API_KEY:
        sys.exit(
            "ERROR: EI_API_KEY is not set.\n"
            "Set it to your Edge Impulse project API key before running this pipeline."
        )

    if PROJECT_ID is None:
        sys.exit(
            "ERROR: PROJECT_ID is not set.\n"
            "Open src/ei_pipeline.py and set PROJECT_ID to your cloned project ID.\n"
            "Find it in EI Studio URL: studio.edgeimpulse.com/studio/XXXXXX"
        )

def hdr(msg): print(f"\n{'-'*60}\n{msg}\n{'-'*60}", flush=True)

def ei_get(path, **kwargs):
    url = f"{STUDIO_URL}/{PROJECT_ID}/{path}"
    return requests.get(url, headers={"x-api-key": API_KEY}, timeout=30, **kwargs)

def ei_post(path, params=None, **kwargs):
    h = {"x-api-key": API_KEY}
    if "json" in kwargs:
        h["Content-Type"] = "application/json"
    return requests.post(url=f"{STUDIO_URL}/{PROJECT_ID}/{path}", headers=h,
                         params=params, timeout=60, **kwargs)

def ei_put(path, **kwargs):
    h = {"x-api-key": API_KEY}
    if "json" in kwargs:
        h["Content-Type"] = "application/json"
    return requests.put(url=f"{STUDIO_URL}/{PROJECT_ID}/{path}", headers=h, timeout=60, **kwargs)

def ei_delete(path, **kwargs):
    return requests.delete(
        url=f"{STUDIO_URL}/{PROJECT_ID}/{path}",
        headers={"x-api-key": API_KEY}, timeout=30, **kwargs
    )


# ── ffmpeg detection ───────────────────────────────────────────────────────────
def find_ffmpeg() -> str | None:
    if shutil.which("ffmpeg"):
        return shutil.which("ffmpeg")
    for base in [
        Path.home() / "AppData/Local/Microsoft/WinGet/Packages",
        Path("C:/ProgramData/chocolatey/bin"),
    ]:
        if base.exists():
            for hit in base.rglob("ffmpeg.exe"):
                return str(hit)
    return None

def ensure_ffmpeg() -> str:
    path = find_ffmpeg()
    if not path:
        sys.exit("ERROR: ffmpeg not found. Install: winget install Gyan.FFmpeg")
    print(f"  ffmpeg: {path}")
    return path


# ── Audio prep ─────────────────────────────────────────────────────────────────
def prep_audio():
    """Convert source audio to 16 kHz mono 1-second WAV clips for EI upload."""
    ffmpeg = ensure_ffmpeg()
    hdr("Prep: converting audio to 16 kHz mono 1-second WAV clips")
    CLIPS_DIR.mkdir(exist_ok=True)

    sources = {}
    if list(_audio_files(MONKEY_DIR)):
        sources["monkey"] = MONKEY_DIR

    if not sources:
        print(f"  No audio source directories found. Add MP3s to {MONKEY_DIR}")
        return

    total = 0
    for label, src_dir in sources.items():
        dst = CLIPS_DIR / label
        dst.mkdir(exist_ok=True)
        n = _split_dir(ffmpeg, src_dir, dst, label)
        total += n
        print(f"  [{label}] {n} clips → will upload as '{LABEL_MAP.get(label, label)}'")

    print(f"\nTotal: {total} clips in {CLIPS_DIR}")
    if total < 20:
        print("WARNING: fewer than 20 clips — consider adding more audio samples.")


def _audio_files(d: Path) -> list:
    return [f for ext in ("*.mp3","*.wav","*.m4a","*.webm","*.ogg","*.flac","*.aac")
            for f in d.glob(ext)]

def _convert_to_wav(ffmpeg: str, src: Path, dst: Path) -> bool:
    r = subprocess.run(
        [ffmpeg, "-y", "-i", str(src),
         "-ar", str(SAMPLE_RATE), "-ac", "1", "-f", "wav", str(dst)],
        capture_output=True, timeout=60,
    )
    return r.returncode == 0

def _split_dir(ffmpeg: str, src: Path, dst: Path, label: str) -> int:
    import soundfile as sf
    import numpy as np

    files = _audio_files(src)
    if not files:
        return 0

    count = 0
    tmp = dst / "_convert_tmp.wav"
    for fpath in files:
        print(f"  {fpath.name}...", end=" ", flush=True)
        if not _convert_to_wav(ffmpeg, fpath, tmp):
            print("FAILED (ffmpeg error)")
            continue
        try:
            data, sr = sf.read(str(tmp))
            if data.ndim > 1:
                data = data[:, 0]
            clip_samples   = int(CLIP_MS * sr / 1000)
            stride_samples = int(STRIDE_MS * sr / 1000)
            pos = 0; n = 0
            while pos + clip_samples <= len(data):
                sf.write(str(dst / f"{label}_{count:04d}.wav"),
                         data[pos : pos + clip_samples], sr, subtype="PCM_16")
                count += 1; n += 1
                pos += stride_samples
            print(f"{len(data)/sr:.1f}s -> {n} clips")
        except Exception as e:
            print(f"FAILED ({e})")

    if tmp.exists():
        tmp.unlink()
    return count


# ── Clear project data ─────────────────────────────────────────────────────────
def clear_project():
    """Delete all samples from the EI project (to wipe tutorial data before upload)."""
    hdr(f"Clear: deleting all samples from project {PROJECT_ID}")
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Collect all sample IDs across both categories
    all_ids = []
    for category in ("training", "testing"):
        offset = 0
        while True:
            r = requests.get(
                f"{STUDIO_URL}/{PROJECT_ID}/raw-data",
                headers={"x-api-key": API_KEY},
                params={"category": category, "limit": 1000, "offset": offset},
            )
            samples = r.json().get("samples", [])
            if not samples:
                break
            all_ids.extend(s["id"] for s in samples)
            offset += len(samples)
            if len(samples) < 1000:
                break

    if not all_ids:
        print("  Nothing to delete")
        return
    print(f"  Found {len(all_ids)} samples — deleting in parallel...")

    def _delete(sample_id):
        r = requests.delete(
            f"{STUDIO_URL}/{PROJECT_ID}/raw-data/{sample_id}",
            headers={"x-api-key": API_KEY},
            timeout=15,
        )
        return r.ok

    done = 0
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(_delete, sid): sid for sid in all_ids}
        for f in as_completed(futures):
            done += 1
            if done % 50 == 0 or done == len(all_ids):
                print(f"  {done}/{len(all_ids)} deleted...", flush=True)

    print(f"  Done — {len(all_ids)} samples deleted")


# ── Upload ─────────────────────────────────────────────────────────────────────
def upload_clips():
    """Upload local clips to EI project, remapping labels via LABEL_MAP."""
    hdr(f"Upload: sending clips to EI project {PROJECT_ID}")
    label_dirs = [d for d in CLIPS_DIR.iterdir() if d.is_dir()] if CLIPS_DIR.exists() else []
    if not label_dirs:
        print("  No clips found — run 'prep' first")
        return

    # Also upload existing noise + unknown clips from old prep if present
    for label_dir in sorted(label_dirs):
        local_label = label_dir.name
        ei_label = LABEL_MAP.get(local_label, local_label)
        clips = sorted(label_dir.glob("*.wav"))
        if not clips:
            continue
        print(f"\n  Uploading {len(clips)} '{local_label}' clips as '{ei_label}'...")
        ok = fail = 0
        for i, clip in enumerate(clips):
            with open(clip, "rb") as f:
                r = requests.post(
                    f"{INGEST_URL}/training/files",
                    headers={"x-api-key": INGEST_KEY, "x-label": ei_label},
                    files={"data": (clip.name, f, "audio/wav")},
                    timeout=30,
                )
            if r.ok:
                ok += 1
            else:
                fail += 1
                print(f"    FAIL [{r.status_code}]: {r.text[:120]}")
            if (i + 1) % 25 == 0:
                print(f"    {i+1}/{len(clips)}...", flush=True)
        print(f"  {ei_label}: {ok} uploaded, {fail} failed")

    print(f"\n  Note: '{CLASS_NEGATIVE}' is the negative catch-all class (alphabetically last).")
    print(f"  EI Syntiant requires exactly one negative class positioned last alphabetically.")
    print(f"\n  Adding EI keywords noise library as '{CLASS_NEGATIVE}' samples...")
    _add_noise_library()


def _add_noise_library():
    """Add EI's keywords noise library, then relabel all noise/unknown → z_openset."""
    import json
    import edgeimpulse as ei_sdk
    import edgeimpulse_api
    from edgeimpulse.experimental import api as exp_api
    ei_sdk.API_KEY = ADMIN_KEY
    client = exp_api.EdgeImpulseApi(key=ADMIN_KEY)

    # Step 1 — add the noise library
    try:
        resp = client.jobs.start_keywords_noise_job(PROJECT_ID)
        job_id = resp.id
        print(f"  Noise library job started: {job_id}")
        _wait_for_job(job_id, interval=10)
    except Exception as e:
        print(f"  Could not start noise library job: {e}")
        print("  Add noise manually: EI Studio → Data acquisition → Add existing data → Keywords noise")
        return

    # Step 2 — relabel noise + unknown → z_openset using batch_edit_labels
    print(f"  Relabeling noise/unknown -> {CLASS_NEGATIVE}...")
    for category in (edgeimpulse_api.RawDataFilterCategory.TRAINING,
                     edgeimpulse_api.RawDataFilterCategory.TESTING):
        try:
            result = client.raw_data.batch_edit_labels(
                project_id=PROJECT_ID,
                category=category,
                edit_sample_label_request=edgeimpulse_api.EditSampleLabelRequest(
                    label=CLASS_NEGATIVE
                ),
                labels=json.dumps(["noise", "unknown"]),
            )
            # If a job was returned, wait for it
            job_id = getattr(result, "id", None) or (result.job.id if hasattr(result, "job") else None)
            if job_id:
                print(f"  Relabel job ({category}): {job_id}")
                _wait_for_job(job_id, interval=5)
            else:
                print(f"  Relabel ({category}): done immediately")
        except Exception as e:
            print(f"  Relabel ({category}) error: {e}")
    print(f"  All noise/unknown samples relabeled to '{CLASS_NEGATIVE}'")


# ── Impulse config ─────────────────────────────────────────────────────────────
def configure_impulse():
    """Verify impulse uses Syntiant DSP block; update if needed."""
    hdr("Impulse: checking Syntiant DSP configuration")

    r = ei_get("impulse")
    if not r.ok:
        print(f"  Could not fetch impulse: {r.status_code} {r.text[:200]}")
        return False

    impulse = r.json().get("impulse", {})
    dsp_blocks = impulse.get("dspBlocks", [])

    if dsp_blocks:
        current_type = dsp_blocks[0].get("type", "")
        if current_type == "syntiant":
            print(f"  Impulse already uses Syntiant DSP block — OK")
            _print_impulse_summary(impulse)
            return True
        else:
            print(f"  WARNING: DSP block type is '{current_type}' (expected 'syntiant')")
            print(f"  The cloned project should already have a Syntiant block.")
            print(f"  Check: https://studio.edgeimpulse.com/studio/{PROJECT_ID}/create-impulse")
            _print_impulse_summary(impulse)
            return True  # proceed anyway — features will tell us if something is wrong

    # No impulse at all — create one with Syntiant block
    print("  No impulse found — creating Syntiant impulse...")
    payload = {
        "inputBlocks": [{
            "id": 1, "type": "time-series", "name": "audio", "title": "Audio (16 kHz)",
            "windowSizeMs": CLIP_MS, "windowIncreaseMs": STRIDE_MS, "frequencyHz": SAMPLE_RATE,
        }],
        "dspBlocks": [{
            "id": 2, "type": "syntiant", "name": "syntiant", "title": "Audio (Syntiant)",
            "axes": ["audio"], "input": 1,
        }],
        "learnBlocks": [{
            "id": 3, "type": "keras", "name": "nn", "title": "NN Classifier",
            "dsp": [2],
        }],
    }
    r2 = ei_post("impulse", json=payload)
    if r2.ok:
        print("  Syntiant impulse created OK")
        return True
    else:
        print(f"  API error [{r2.status_code}]: {r2.text[:400]}")
        print(f"\n  → Configure manually: https://studio.edgeimpulse.com/studio/{PROJECT_ID}/create-impulse")
        print("    Processing block: Audio (Syntiant)   Learning: Classification")
        return False

def _print_impulse_summary(impulse):
    for b in impulse.get("inputBlocks", []):
        print(f"    Input:  {b.get('title')} — {b.get('frequencyHz')} Hz, {b.get('windowSizeMs')} ms window")
    for b in impulse.get("dspBlocks", []):
        print(f"    DSP:    {b.get('title')} (type={b.get('type')})")
    for b in impulse.get("learnBlocks", []):
        print(f"    Learn:  {b.get('title')}")


# ── Training ───────────────────────────────────────────────────────────────────
def start_training():
    hdr("Train: generating features + training")

    r_imp = ei_get("impulse")
    if not r_imp.ok:
        print("  Could not fetch impulse")
        return None
    impulse = r_imp.json().get("impulse", {})
    dsp_id   = impulse["dspBlocks"][0]["id"]
    learn_id = impulse["learnBlocks"][0]["id"]
    dsp_type = impulse["dspBlocks"][0].get("type")

    # Feature generation — direct REST (EI SDK generate_features_job hangs)
    print(f"  Generating DSP features (dspId={dsp_id}, type={dsp_type})...")
    r_gen = ei_post("jobs/generate-features",
                    json={"dspId": dsp_id, "calculateFeatureImportance": False})
    if not r_gen.ok:
        print(f"  Feature gen failed [{r_gen.status_code}]: {r_gen.text[:200]}")
        return None
    gen_job_id = r_gen.json()["id"]
    print(f"  Feature gen job: {gen_job_id}")
    if not _wait_for_job(gen_job_id):
        print("  Feature generation failed")
        return None

    # Training — direct REST (endpoint: /jobs/train/keras/{learnId})
    print(f"\n  Training Keras model (learn block {learn_id})...")
    r_train = ei_post(f"jobs/train/keras/{learn_id}",
                      json={"mode": "visual", "trainingCycles": 50,
                            "learningRate": 0.0005, "trainTestSplit": 0.8,
                            "autoClassWeights": False})
    if not r_train.ok:
        print(f"  Training start failed [{r_train.status_code}]: {r_train.text[:200]}")
        return None
    job_id = r_train.json()["id"]
    print(f"  Training job: {job_id}")
    return job_id


def train():
    if not configure_impulse():
        return
    job_id = start_training()
    if job_id:
        ok = _wait_for_job(job_id)
        if ok:
            print("\nTraining complete — run: python src/ei_pipeline.py download")
        else:
            print("\nTraining failed — check EI Studio for logs")


def _wait_for_job(job_id, interval=15):
    """Poll /jobs/{id}/status until finished or failed.
    EI uses 'finished' (timestamp or null) + 'finishedSuccessful' (bool), not a status string.
    """
    print(f"\nWaiting for job {job_id}...")
    while True:
        r = ei_get(f"jobs/{job_id}/status")
        if r.ok:
            j = r.json().get("job", {})
            finished = j.get("finished")
            ok       = j.get("finishedSuccessful")
            pct      = j.get("percentDone", "")
            t        = time.strftime('%H:%M:%S')
            if finished:
                if ok:
                    print(f"  [{t}] done ok=True"); return True
                else:
                    print(f"  [{t}] done ok=False (failed)"); return False
            else:
                print(f"  [{t}] running {pct}%", flush=True)
        else:
            print(f"  [{time.strftime('%H:%M:%S')}] HTTP {r.status_code}", flush=True)
        time.sleep(interval)


# ── Status ─────────────────────────────────────────────────────────────────────
def check_status():
    hdr(f"Status: project {PROJECT_ID}")
    import edgeimpulse as ei_sdk
    ei_sdk.API_KEY = ADMIN_KEY
    from edgeimpulse.experimental import api as exp_api
    client = exp_api.EdgeImpulseApi(key=ADMIN_KEY)

    jobs_resp = client.jobs.list_all_jobs(PROJECT_ID)
    jobs = jobs_resp.jobs or []
    if not jobs:
        print("  No jobs")
    for j in jobs[:6]:
        pct = getattr(j, 'percent_done', 0) or 0
        print(f"  Job {j.id}: {getattr(j,'job_type','?')} — {j.status} {pct}%")

    r = ei_get("raw-data/stats")
    if r.ok and r.json().get("success"):
        stats = r.json()
        for split in ("train", "test"):
            sdata = stats.get(split, {})
            if sdata:
                print(f"\n  {split}: {sdata.get('totalLengthMs', 0)//1000}s total")
                for cls in sdata.get("classes", []):
                    print(f"    {cls['label']}: {cls['totalLengthMs']//1000}s")


# ── Download ───────────────────────────────────────────────────────────────────
def build_deployment(dtype="syntiant-nicla-ndp120"):
    """Trigger a deployment build job and wait for it to complete."""
    hdr(f"Build: compiling {dtype} deployment")
    r = ei_post("jobs/build-ondevice-model",
                json={"engine": "syntiant"},
                params={"type": dtype})  # type goes as query param
    if not r.ok or not r.json().get("id"):
        print(f"  Build start failed [{r.status_code}]: {r.text[:200]}")
        return False
    job_id = r.json()["id"]
    print(f"  Build job: {job_id}")
    return _wait_for_job(job_id, interval=15)


def download_deployment():
    hdr("Download: fetching Syntiant NDP120 deployment")
    DEPLOY_DIR.mkdir(exist_ok=True)

    dtype = "syntiant-nicla-ndp120"
    print(f"  Triggering build for {dtype}...")
    if not build_deployment(dtype):
        print("  Build failed — cannot download")
        return

    print(f"\n  Downloading {dtype}...")
    for dtype in ("syntiant-nicla-ndp120", "syntiant-ndp120-lib", "syntiant-ndp120", "syntiant"):
        print(f"  Trying deployment target: {dtype}...")
        r = requests.get(
            f"{STUDIO_URL}/{PROJECT_ID}/deployment/download",
            headers={"x-api-key": ADMIN_KEY},
            params={"type": dtype},
            timeout=120,
            stream=True,
        )
        ct = r.headers.get("content-type", "")
        if r.ok and "zip" in ct:
            zip_name = f"ei-syntiant-{dtype}.zip"
            zip_path = DEPLOY_DIR / zip_name
            with open(zip_path, "wb") as f:
                for chunk in r.iter_content(65536):
                    f.write(chunk)
            size_kb = zip_path.stat().st_size // 1024
            print(f"  Downloaded: {zip_name} ({size_kb} KB)")

            extract_dir = DEPLOY_DIR / dtype
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(extract_dir)
                print("  Contents:")
                for name in z.namelist():
                    print(f"    {name}")

            synpkg = sorted(extract_dir.rglob("*.synpkg"))
            if synpkg:
                print(f"\n  .synpkg files ready:")
                for p in synpkg:
                    print(f"    {p}  ({p.stat().st_size // 1024} KB)")
                print("\n  Next steps:")
                print("  1. Flash Syntiant_upload_fw_ymodem.ino to the board")
                print("  2. Use YMODEM to upload each .synpkg to the board's SPI flash")
                print(f"  3. Update NDP.load() call in src/main.ino to match .synpkg filenames")
                print(f"  4. Set TARGET_LABEL = \"{CLASS_POSITIVE}\" in src/main.ino")
                print("  5. Flash src/main.ino")
            else:
                print("  No .synpkg files in ZIP — check EI Studio for errors")
            return
        else:
            print(f"    [{r.status_code}] {r.text[:100]}")

    print(f"\n  Could not download Syntiant deployment.")
    print(f"  Check: https://studio.edgeimpulse.com/studio/{PROJECT_ID}/deployment")
    print("  Note: Syntiant EULA may need to be accepted in EI Studio first.")


# ── Info ───────────────────────────────────────────────────────────────────────
def info():
    hdr(f"Info: EI project {PROJECT_ID}")
    import edgeimpulse as ei_sdk
    ei_sdk.API_KEY = ADMIN_KEY
    from edgeimpulse.experimental import api as exp_api
    client = exp_api.EdgeImpulseApi(key=ADMIN_KEY)

    try:
        from collections import Counter
        counts = Counter()
        for category in ("training", "testing"):
            raw = client.raw_data.list_samples(PROJECT_ID, category=category, limit=1000)
            for s in (raw.samples or []):
                counts[f"{category}/{s.label}"] += 1
        if counts:
            print("\n  Samples on server:")
            for key, n in sorted(counts.items()):
                print(f"    {key}: {n}")
        else:
            print("\n  No samples on server yet")
    except Exception as e:
        print(f"  Could not fetch sample counts: {e}")

    r = ei_get("impulse")
    if r.ok:
        impulse = r.json().get("impulse", {})
        if impulse.get("inputBlocks"):
            print("\n  Current impulse:")
            _print_impulse_summary(impulse)

    if CLIPS_DIR.exists():
        print("\n  Local clips prepared:")
        for label_dir in sorted(CLIPS_DIR.iterdir()):
            clips = list(label_dir.glob("*.wav"))
            if clips:
                ei_label = LABEL_MAP.get(label_dir.name, label_dir.name)
                print(f"    {label_dir.name}: {len(clips)} clips (uploads as '{ei_label}')")


# ── Main ───────────────────────────────────────────────────────────────────────
def relabel_noise():
    """Relabel all noise/unknown samples in the project to z_openset."""
    import json
    import edgeimpulse_api
    from edgeimpulse.experimental import api as exp_api
    client = exp_api.EdgeImpulseApi(key=ADMIN_KEY)
    hdr(f"Relabel: noise/unknown -> {CLASS_NEGATIVE} in project {PROJECT_ID}")
    for category in (edgeimpulse_api.RawDataFilterCategory.TRAINING,
                     edgeimpulse_api.RawDataFilterCategory.TESTING):
        try:
            result = client.raw_data.batch_edit_labels(
                project_id=PROJECT_ID,
                category=category,
                edit_sample_label_request=edgeimpulse_api.EditSampleLabelRequest(
                    label=CLASS_NEGATIVE
                ),
                labels=json.dumps(["noise", "unknown"]),
            )
            job_id = getattr(result, "id", None) or (result.job.id if hasattr(result, "job") else None)
            if job_id:
                print(f"  Relabel job ({category}): {job_id}")
                _wait_for_job(job_id, interval=5)
            else:
                print(f"  Relabel ({category}): done immediately")
        except Exception as e:
            print(f"  Relabel ({category}) error: {e}")
    print(f"  Done")


COMMANDS = {
    "prep":     prep_audio,
    "clear":    clear_project,
    "upload":   upload_clips,
    "relabel":  relabel_noise,
    "impulse":  configure_impulse,
    "train":    train,
    "status":   check_status,
    "download": download_deployment,
    "info":     info,
    "all": lambda: [
        clear_project(),
        upload_clips(),
        configure_impulse(),
        train(),
        download_deployment(),
    ],
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "help"
    if cmd not in COMMANDS:
        print(__doc__)
        sys.exit(0)
    _check_project_id()
    COMMANDS[cmd]()
