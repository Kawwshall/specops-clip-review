# zkit

Two tools for SPEC-OPS field operations, served from a single Vercel deployment.

**→ [zkits.vercel.app](https://zkits.vercel.app)**

---

## Z-Kit Guide — `zkits.vercel.app`

Field operations reference for the egocentric recording kit.

- Component index with photos — click any part to inspect
- Assembly walkthrough (phase 1)
- Bag packing guide (phase 1)
- Field checks in order (phase 2)
- Links and deployment report
- FAQs

---

## Clip Review — `zkits.vercel.app/clip-review`

Post-shift tool for reviewing MCAP footage from ZEDREC cards.

- Plug in the ZEDREC SD card — drive is detected automatically
- Lists all clips sorted chronologically with real durations
- Click any clip to play it in the browser — no extra software
- Converts H.265 on the fly; falls back to H.264 re-encode if needed
- Clip timing cached to disk so repeat loads are instant

---

## Stack

| Part | What |
|---|---|
| `server.py` | Python HTTP server — MCAP parsing, ffmpeg conversion via `imageio-ffmpeg` |
| `index.html` | Single-file Clip Review app UI — drive picker, clip list, video player |
| `landing/index.html` | Z-Kit Guide static page |
| `landing/clip-review.html` | Clip Review landing/download page |
| `.github/workflows/build.yml` | CI — builds Windows `.exe` + macOS `.dmg`, publishes to GitHub Releases |

---

## Dev setup

Requires Python 3.9+.

```bash
pip install imageio-ffmpeg
python server.py
# open http://127.0.0.1:8765
```

For the landing pages:

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

Drag-to-Applications DMG. No Python or Xcode on the target machine — installs a venv in `~/.clipreview` on first launch.

### Windows — .exe

```bash
pip install pyinstaller pillow imageio-ffmpeg
pyinstaller --clean --noconfirm specops.spec
# outputs dist/ClipReview.exe
```

Single self-contained executable. No install required.

### CI (GitHub Actions)

Every push to `main`:
1. Builds Windows `.exe` and macOS `.dmg` in parallel
2. Publishes both to the rolling `latest` GitHub Release
3. Landing pages auto-deploy to Vercel

---

## macOS first-launch note

Ad-hoc signed (no Apple Developer certificate). If macOS shows "unverified developer":

> System Settings → Privacy & Security → scroll down → Open Anyway

One-time step.

---

## Limits

- Compressed MCAP chunks (`zstd`, `lz4`) are not decoded
- Video conversion is optimised for speed, not archive quality
- Clip Review server must run on the machine with the SD card attached
