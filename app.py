# app.py
from flask import Flask, request, jsonify, render_template
from manager import SourceManager
from streamer import Streamer
# from hardware import GPIOController

DEFAULT_SOURCE='audio1'
app = Flask(__name__)
sources = SourceManager(default_source=DEFAULT_SOURCE)
streamer = Streamer(default_source=sources.sources[DEFAULT_SOURCE])

# Callback from GPIO controller
def gpio_switch_callback(name):
    print(f"[GPIO] Toggling to {name}")
    try:
        old, new = sources.switch_to(name)
        old_path = sources.sources.get(old, sources.sources[new])
        new_path = sources.sources[new]
        streamer.crossfade_stream(old_path, new_path)
    except Exception as e:
        print("[GPIO] Failed to switch:", e)

# Start GPIO listener
# gpio = GPIOController(switch_callback=gpio_switch_callback, primary_source="cam1", secondary_source="cam2")

@app.route("/switch_source", methods=["POST"])
def switch_source():
    try:
        print('[MAIN] Trying to switch source')
        name = request.json["name"]
        # gpio.current = name  # sync LED state
        old, new = sources.switch_to(name)

        old_path = sources.sources.get(old)  # might be None
        new_path = sources.sources[new]

        if new_path == old_path:
            print('Source Already Active')
            return jsonify({'status': "Source Already Active"})
        else:
            print('Attempting Crossfade')
            streamer.crossfade_stream(old_path, new_path)

        # gpio._update_led()
        return jsonify({"status": "switching", "from": old, "to": new})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route("/add_source", methods=["POST"])
def add_source():
    data = request.json
    name = data["name"]
    path = data["path"]

    if name in sources.sources:
        return jsonify({"error": f"Source '{name}' already exists."}), 400

    sources.add_source(name, path)
    return jsonify({"status": "added", "name": name})

@app.route("/remove_source", methods=["POST"])
def remove_source():
    name = request.json["name"]
    sources.remove_source(name)
    return jsonify({"status": "removed", "name": name})

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "active": sources.get_active(),
        "sources": sources.sources
    })

@app.route("/")
def index():
    return render_template("index.html")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
