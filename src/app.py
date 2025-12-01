# src/app.py

"""
Flask API for the Multithreaded Simulator.
Frontend (HTML/CSS/JS) will communicate with this server to:
- Get state
- Add threads
- Control simulation (start/pause/step)
- Change scheduler, quantum, model
"""

from flask import Flask, jsonify, request, send_from_directory
import os

from simulator.controller import SimulationController


# Flask Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")

app = Flask(
    __name__,
    static_folder=STATIC_DIR,
    template_folder=TEMPLATES_DIR
)


# Create global controller instance
controller = SimulationController(
    num_kernel_threads=2,
    model=None  # default Many-to-Many
)


# -----------------------------
# API ENDPOINTS
# -----------------------------

@app.route("/api/state", methods=["GET"])
def api_state():
    """Return full simulation snapshot"""
    return jsonify(controller.get_state_snapshot())


@app.route("/api/start", methods=["POST"])
def api_start():
    controller.start()
    return jsonify({"ok": True})


@app.route("/api/pause", methods=["POST"])
def api_pause():
    controller.pause()
    return jsonify({"ok": True})


@app.route("/api/step", methods=["POST"])
def api_step():
    controller.step()
    return jsonify({"ok": True})


@app.route("/api/add_thread", methods=["POST"])
def api_add_thread():
    data = request.json or {}
    burst = int(data.get("burst", 10))
    priority = int(data.get("priority", 0))
    name = data.get("name")

    t = controller.add_thread(burst, priority, name)

    return jsonify({
        "ok": True,
        "thread": {
            "id": t.id,
            "name": t.name,
            "priority": t.priority,
            "burst": t.total_burst
        }
    })


@app.route("/api/set", methods=["POST"])
def api_set():
    """
    Set model, scheduler, quantum
    Example payload:
    {
        "model": "MANY_TO_ONE",
        "scheduler": "RR",
        "quantum": 2
    }
    """
    data = request.json or {}

    if "model" in data:
        controller.set_model(data["model"])

    if "scheduler" in data:
        controller.set_scheduler(data["scheduler"])

    if "quantum" in data:
        controller.set_quantum(int(data["quantum"]))

    return jsonify({"ok": True})


# Serve index.html
@app.route("/", methods=["GET"])
def index():
    return send_from_directory(TEMPLATES_DIR, "index.html")


# For CSS/JS
@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory(STATIC_DIR, path)


# -----------------------------
# RUN THE SERVER
# -----------------------------
if __name__ == "__main__":
    print("Starting Flask backend on http://127.0.0.1:5000/")
    app.run(host="0.0.0.0", port=5000, debug=True)
