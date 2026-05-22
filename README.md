# SPEC-OPS Clip Review Console

This tool is for fast review of MCAP clips from device SD cards.

## Run

```bat
start-viewer.bat
```

Then open `http://127.0.0.1:8765`.

## Team workflow

1. Mount or copy an SD card folder to a local drive.
2. In the app, enter the root path such as `D:\recordings` or `E:\device-01`.
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

For the team, ship this folder as a small local app:

- `.venv`
- `index.html`
- `server.py`
- `start-viewer.bat`
- `spec-ops-logo.png`

Each teammate runs `start-viewer.bat` and opens `http://127.0.0.1:8765`.

## Limits

- `zstd` and `lz4` compressed MCAP chunks are not decoded yet.
- Preview conversion is optimized for speed, not archive quality.
- The scan path must be reachable on the local machine that runs the helper.
