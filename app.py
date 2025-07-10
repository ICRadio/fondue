# app.py
from flask import Flask, request, jsonify, render_template
from manager import SourceManager
from streamer import Streamer
# from hardware import GPIOController
import os
import sys
import atexit
import logging
from logging.handlers import RotatingFileHandler

LOG_FILE = '/var/log/fondue.log'

log_handler = RotatingFileHandler(LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
log_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logging.basicConfig(
    level=logging.INFO,
    handlers=[log_handler, logging.StreamHandler(sys.stdout)]
)

logger = logging.getLogger(__name__)

DEFAULT_SOURCE = "mp3"
OUTPUT_PATH = "icecast://source:mArc0n1@icr-emmental.media.su.ic.ac.uk:8888/radio"

app = Flask(__name__)
sources = SourceManager(default_source=DEFAULT_SOURCE)
streamer = Streamer(
    output_path=OUTPUT_PATH,
    default_source=sources.sources[DEFAULT_SOURCE]
)


# Callback from GPIO controller
def gpio_switch_callback(name):
    logger.info(f"[GPIO] Toggling to {name}")
    try:
        old, new = sources.switch_to(name)
        old_path = sources.sources.get(old, sources.sources[new])
        new_path = sources.sources[new]
        streamer.crossfade_stream(old_path, new_path)
    except Exception as e:
        logger.info("[GPIO] Failed to switch:", e)

# Start GPIO listener
# gpio = GPIOController(switch_callback=gpio_switch_callback, primary_source="cam1", secondary_source="cam2")


@app.route("/switch_source", methods=["POST"])
def switch_source():
    try:
        name = request.json["name"]
        # gpio.current = name  # sync LED state
        old, new = sources.switch_to(name)
        if old == new:
            logger.info('Source Already Active')
            return jsonify({'status': "Source Already Active"})

        logger.info('[MAIN] Crossfading...')
        new_path = sources.sources[new]
        status = streamer.crossfade_stream(new_path, duration=2)
        if status is False:
            # If crossfade fails, revert to old source
            sources.switch_to(old)
            logger.error(f'[MAIN] Crossfade failed, remaining with old source: {old}')
            return jsonify({"error": "Failed to crossfade stream."}), 500
        return jsonify({"status": "switching", "from": old, "to": new})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/remove_source", methods=["POST"])
def remove_source():
    name = request.json["name"]
    sources.remove_source(name)
    return jsonify({"status": "removed", "name": name})


@app.route("/add_source", methods=["POST"])
def add_source():
    data = request.json
    name = data["name"]
    path = data["path"]

    if name in sources.sources:
        return jsonify({"error": f"Source '{name}' already exists."}), 400

    sources.add_source(name, path)
    return jsonify({"status": "added", "name": name})


@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "active": sources.get_active(),
        "sources": sources.sources
    })


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/logs", methods=["GET"])
def get_logs():
    try:
        with open(LOG_FILE, "r") as f:
            # Only return last 100 lines
            lines = f.readlines()[-100:]
        return "<pre>" + "".join(lines) + "</pre>"
    except Exception as e:
        logger.error("Failed to read log file: %s", e)
        return jsonify({"error": "Could not read logs."}), 500


def cleanup_pipe(signum, frame):
    logger.info('CLEANING UP')
    os.system(
        'rm -rf /tmp/input_pipe'
    )
    sys.exit(0)
    return


# signal.signal(signal.SIGINT, cleanup_pipe)
atexit.register(streamer.shutdown)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
