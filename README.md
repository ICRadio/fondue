# Fondue

Fondue is a tiny Flask control surface that lets ICRadio operators point an FFmpeg pipeline at different audio sources (studio codec, RTMP feeds, local files, etc.) and publish the blended output to Icecast. The backend keeps a named list of sources, persists them to `sources.json`, and uses the `Streamer` helper to validate streams and perform smooth crossfades before writing to `/tmp/input_pipe` for re-encoding.

## Features
- Web UI for viewing, adding, removing, and switching audio sources
- Seamless source changes via FFmpeg crossfades with configurable durations
- Persistent source catalogue (`sources.json`) managed by `SourceManager`
- Optional GPIO integration (see `hardware.py`) for a physical toggle button + LED
- FIFO watchdog that automatically rebuilds `/tmp/input_pipe` if FFmpeg stalls, then resumes the active source within a second
- Basic log viewer exposed through `/logs` so operators can read rotating logs remotely

## Project Layout
| Path | Purpose |
| --- | --- |
| `app.py` | Flask entry point, REST API, log endpoint, and HTML renderer. |
| `streamer.py` | Manages FFmpeg writer/encoder processes, stream validation, and crossfades. |
| `manager.py` | Persists source definitions and tracks the currently-active entry. |
| `templates/index.html` | Minimal control panel for operators. |
| `static/script.js` | Front-end logic for CRUD actions and polling `/status`. |
| `hardware.py` | Raspberry Pi GPIO button/LED helper (optional). |
| `fondue.service` | Example systemd unit for auto-starting the app on boot. |

## Quick Start
1. Install prerequisites  
   - Python 3.10+  
   - FFmpeg (available via `brew install ffmpeg`, `apt install ffmpeg`, etc.)  
   - (Optional) Raspberry Pi + `RPi.GPIO` if you want hardware toggles
2. Create and activate a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install -r requirements.txt
   ```
3. Configure sources by editing `sources.json` or using the “Add Source” form in the UI. Each entry’s value is any FFmpeg-readable input (`hw:CARD=CODEC`, `rtmp://…`, local file path, etc.).
4. Start the server:
   ```bash
   python app.py
   ```
   By default Flask binds to `0.0.0.0:8000`, serves the control panel at `/`, and exposes REST endpoints consumed by the front-end.

## Docker Option
Prefer an isolated runtime with FFmpeg baked in?

```bash
docker build -t fondue .
docker run --name fondue \
  -p 8000:8000 \
  -v "$(pwd)/sources.json:/app/sources.json" \
  -v "$(pwd)/fondue.log:/app/fondue.log" \
  fondue
```

This mirrors the local setup but uses the container’s Python + FFmpeg stack. Rebuild the image after code changes (`docker build -t fondue .`) and restart the container.

## API Overview
| Method | Path | Description |
| --- | --- | --- |
| `GET /status` | Returns the active source name and current `sources.json` contents. |
| `POST /switch_source` | Payload `{"name": "<source>"}` triggers a crossfade to that source. |
| `POST /add_source` | Adds a named source; body requires `name` and `path`. |
| `POST /remove_source` | Removes a source by name. |
| `GET /logs` | Query params `file` (fondue/ffmpeg) and `lines` (1-1000); returns log text. |

## Logging
- `app.py` configures a `RotatingFileHandler` that writes `fondue.log` (5 MB per file, 3 backups) and mirrors messages to stdout. All Flask routes, source-switch events, and streamer diagnostics flow through this logger.
- The `/logs` endpoint is a thin wrapper that reads the tail of whichever key is requested in `ALLOWED_LOGS`. By default two keys are exposed: `fondue` (application log) and `ffmpeg` (if you pipe FFmpeg stderr into `ffmpeg.log`).
- When running inside Docker, bind-mount the log files you care about so the rotation persists beyond the container lifecycle (see “Docker Option” above).
- Log level defaults to `INFO`; edit the `logging.basicConfig` call if you need more verbose output (e.g., `DEBUG` during troubleshooting).

## FIFO Watchdog
- The `Streamer` class continuously tails `/tmp/input_pipe` and tracks its last write time. If FFmpeg stops writing for longer than `fifo_idle_timeout` (15 s by default), the watchdog tears down the FIFO, restarts the encoder, and reattaches the current source automatically.
- Watchdog timing can be tuned via the `fifo_watchdog_interval` (polling cadence) and `fifo_idle_timeout` arguments when instantiating `Streamer`.
- Operators no longer need to manually delete the pipe after an unexpected crash, but log entries tagged `[STREAMER] FIFO idle` will still call out when an automatic reset happened so you can investigate the underlying cause.

## Deployment Notes
- `OUTPUT_PATH` in `app.py` points to the Icecast mount (update credentials/URI as needed).
- The `fondue.service` unit file shows how to run the app under systemd so it restarts automatically and starts after networking is up.
- Always keep `/tmp/input_pipe` clear before restarting; `Streamer.shutdown()` (registered via `atexit`) handles cleanup when the Flask process exits normally.

For development specifics (tooling, workflows, testing notes) see `DEVELOPING.md`.
