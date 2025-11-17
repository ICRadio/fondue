# Developing Fondue

This document captures how to work on the Fondue codebase locally and how to test the FFmpeg-driven audio pipeline before deploying it to ICRadio’s infrastructure.

## Prerequisites
- **Python** 3.10+ (the project uses stock Flask only)
- **FFmpeg** accessible from `$PATH` (the streamer spawns multiple FFmpeg processes)
- **Icecast / local audio sink** to receive the encoded output, or a file path if you want to test locally
- **RPi.GPIO** and a Raspberry Pi with button/LED wiring if you want to exercise `hardware.py`

## Environment Setup
```bash
git clone <repo> fondue && cd fondue
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Optional: install development helpers (linting, type checking, etc.) to taste; the repo does not enforce a particular toolchain yet.

## Configuration
1. **Sources** – edit `sources.json` to seed the list of audio inputs. Each value can be:
   - ALSA devices such as `hw:CARD=CODEC`
   - URLs FFmpeg understands (`rtmp://`, `http(s)://`, `icecast://`, etc.)
   - Paths to files on disk; they are looped endlessly
2. **Output** – update `OUTPUT_PATH` in `app.py` to point at a development destination (e.g., `output.mp3` while testing locally, or a staging Icecast mount).
3. **Logging** – rotating logs are written to `fondue.log`; FFmpeg stderr can be piped to `ffmpeg.log` if you configure logging accordingly.

## Running Locally
```bash
source .venv/bin/activate
python app.py
```
The Flask server binds to `0.0.0.0:8000`. Visit `http://localhost:8000` to open the control panel. Updating sources via the UI automatically persists them to `sources.json`.

When switching sources the backend:
1. Validates the requested source by briefly probing it with FFmpeg.
2. Crossfades from the old to the new input and writes PCM samples into `/tmp/input_pipe`.
3. A second FFmpeg process (`_start_output_proc`) encodes the FIFO into MP3 and pushes it to `OUTPUT_PATH`.

## Docker Workflow
> Why Docker? Shipping the FFmpeg runtime alongside the Python code makes it trivial to run the control app anywhere without touching the base OS.

Build the image (runs pip install + installs FFmpeg):
```bash
docker build -t fondue .
```

Run the container and publish the Flask port. Bind-mount `sources.json` and any log files you want persisted outside the container:
```bash
docker run --name fondue \
  -p 8000:8000 \
  -v "$(pwd)/sources.json:/app/sources.json" \
  -v "$(pwd)/fondue.log:/app/fondue.log" \
  fondue
```

The app still respects `OUTPUT_PATH` in `app.py`. Adjust that file (or add your own environment-variable driven logic) before building the image if you need different Icecast credentials for production vs. development.

To update code, rebuild the image and restart the container:
```bash
docker build -t fondue .
docker stop fondue && docker rm fondue
docker run ... fondue
```

## Useful Commands
- **Check log tail** – `tail -f fondue.log`
- **Inspect active FFmpeg jobs** – `ps -ef | grep ffmpeg`
- **Clean stuck FIFO** – delete `/tmp/input_pipe` if the app exits unexpectedly before `Streamer.shutdown()` runs.

## Hardware Testing
`hardware.py` contains a simple `GPIOController` that toggles between two named sources with a push button and mirrors the state via an LED. To test:
1. Wire a button between GPIO 17 and ground, and an LED (with resistor) between GPIO 27 and ground.
2. Instantiate `GPIOController` in `app.py` (uncomment the provided lines) with the appropriate source names.
3. Deploy to a Raspberry Pi running the Flask app; pressing the button should call back into `gpio_switch_callback`.

## Deployment Workflow
1. Copy the repo to the target host (e.g., `/home/icradio/fondue`).
2. Create/activate a virtualenv and install dependencies as above.
3. Create `/etc/systemd/system/fondue.service` based on the provided example, adjusting paths, user, and environment variables.
4. `sudo systemctl daemon-reload && sudo systemctl enable --now fondue`.

## Troubleshooting
- **Crossfade fails immediately** – check `fondue.log` for “Invalid stream URL”; the validation probe may not reach the source.
- **Dead air after restart** – ensure `/tmp/input_pipe` was removed; stale FIFOs can block FFmpeg from writing.
- **Log endpoint returns 500** – verify the log file key passed to `/logs?file=<key>` exists in `ALLOWED_LOGS`.

Feel free to document additional workflows (testing, formatting rules, etc.) here as they evolve.
