# SPEC-OPS Clip Review

Post-shift tool for reviewing MCAP footage from ZEDREC cards.
Auto-detects the drive, lists all clips with duration, plays video directly in the browser.

**Download → [zkits.vercel.app/clip-review](https://zkits.vercel.app/clip-review)**

---

## What it does

- Plug in the ZEDREC SD card — drive is detected automatically
- Lists all MCAP clips sorted chronologically with real durations
- Click any clip to play it in the browser (no extra software)
- Converts H.265 on the fly; falls back to H.264 re-encode if the browser can't decode it
- Clip timing is cached to disk so repeat loads are instant

---

## Stack

| Part | What |
|---|---|
| `server.py` | Python HTTP server — MCAP parsing, ffmpeg conversion via `imageio-ffmpeg` |
| `index.html` | Single-file app UI — drive picker, clip list, video player |
| `landing/` | Static landing page deployed to Vercel (`zkits.vercel.app`) |
| `.github/workflows/build.yml` | CI — builds Windows `.exe` + macOS `.dmg`, publishes to GitHub Releases |

---

## Dev setup

Requires Python 3.9+.

```bash
pip install imageio-ffmpeg
python server.py
# open http://127.0.0.1:8765
```

For the landing page, any static file server works:

```bash
cd landing
python -m http.server 3000
# open http://localhost:3000
```

---

## Building

### macOS — DMG

```bash
bash build-mac.sh
# outputs ClipReview-mac.dmg
```

Produces a drag-to-Applications DMG. No Python or Xcode required on the target machine — the app installs a venv in `~/.clipreview` on first launch.

### Windows — .exe

```bash
pip install pyinstaller pillow imageio-ffmpeg
pyinstaller --clean --noconfirm specops.spec
# outputs dist/ClipReview.exe
```

Single self-contained executable. No install required.

### CI (GitHub Actions)

Every push to `main` triggers `.github/workflows/build.yml`:
1. Builds Windows `.exe` and macOS `.dmg` in parallel
2. Publishes both to the rolling `latest` GitHub Release
3. Landing page auto-deploys to Vercel

---

## macOS first-launch note

The app is ad-hoc signed (no Apple Developer certificate). If macOS shows "unverified developer":

> System Settings → Privacy & Security → scroll down → Open Anyway

One-time step — never appears again.

---

## Limits

- Compressed MCAP chunks (`zstd`, `lz4`) are not decoded
- Video conversion is optimised for speed, not archive quality
- Server must run on the machine with the SD card attached
