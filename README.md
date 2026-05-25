# SPEC-OPS Clip Review Console

This tool is for fast review of MCAP clips from device SD cards.

## Run

**Windows**
```bat
start-viewer.bat
```

**macOS**
```bash
./start-viewer.sh
```

Then open `http://127.0.0.1:8765`.

## Team workflow

1. Mount or copy an SD card / USB drive.
2. In the app, enter the root path — e.g. `D:\recordings` on Windows or `/Volumes/SD-CARD/recordings` on Mac.
3. Click `Scan Drive`.
4. Pick a clip from the indexed list.
5. Pick a video topic.
6. Click `Fast Play`.

If the browser cannot decode H.265, the app automatically uses a smaller H.264 preview conversion.

## Supported

- Server-side scan of `.mcap` clips under a drive or folder.
- Server-side topic inspection for local clips.
- Foxglove `CompressedVideo` local conversion to browser-playable preview MP4.
- JPEG/PNG/WebP frame playback for image-message MCAP files.
- Custom player controls: play, pause, resume, seek, skip, fullscreen.

## Deployment

**Windows** — ship the built `ClipReview.exe` (single file, no Python needed).

**macOS** — build with `./build-mac.sh` (signs + packages automatically):
```bash
./build-mac.sh
# outputs ClipReview-mac.zip
```
Teammates unzip, drag `ClipReview.app` to `/Applications`, and double-click — no Python needed.

**Without building** — ship this folder and run with `start-viewer.sh` (macOS) or `start-viewer.bat` (Windows). Python 3.9+ required.

## macOS Gatekeeper

The app is ad-hoc signed (no paid Apple certificate). If macOS shows **"ClipReview cannot be opened because the developer cannot be verified"**:

**Option A — right-click open (one-time prompt):**
1. Right-click `ClipReview.app` → **Open**
2. Click **Open** in the dialog

**Option B — strip quarantine in Terminal:**
```bash
xattr -rd com.apple.quarantine /Applications/ClipReview.app
```

After either option the app opens normally every time.

## Limits

- `zstd` and `lz4` compressed MCAP chunks are not decoded yet.
- Preview conversion is optimized for speed, not archive quality.
- The scan path must be reachable on the local machine that runs the helper.
