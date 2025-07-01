# app.py
from flask import Flask, request, jsonify
from manager import SourceManager
from streamer import Streamer

app = Flask(__name__)
sources = SourceManager()
streamer = Streamer()

@app.route("/add_source", methods=["POST"])
def add_source():
    data = request.json
    sources.add_source(data["name"], data["path"])
    return jsonify({"status": "added", "name": data["name"]})

@app.route("/remove_source", methods=["POST"])
def remove_source():
    name = request.json["name"]
    sources.remove_source(name)
    return jsonify({"status": "removed", "name": name})

@app.route("/switch_source", methods=["POST"])
def switch_source():
    try:
        name = request.json["name"]
        old, new = sources.switch_to(name)
        if old:
            old_path = sources.get_sources()[old]
        else:
            old_path = sources.get_sources()[new]  # fallback
        new_path = sources.get_sources()[new]

        streamer.crossfade_stream(old_path, new_path)
        return jsonify({"status": "switching", "from": old, "to": new})
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

@app.route("/status", methods=["GET"])
def status():
    return jsonify({
        "active": sources.get_active(),
        "sources": sources.get_sources()
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
