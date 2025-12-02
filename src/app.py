# src/app.py

"""
Flask API for the Multithreaded Simulator.
Frontend (HTML/CSS/JS) will communicate with this server to:
- Get state
- Add threads
- Control simulation (start/pause/step/reset)
- Manage semaphores & monitors
"""

from flask import Flask, jsonify, request, send_from_directory
import os

from src.simulator.controller import SimulationController

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "..", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "..", "static")

app = Flask(__name__, static_folder=STATIC_DIR, template_folder=TEMPLATES_DIR)

# single controller instance
controller = SimulationController(num_kernel_threads=2)

def init_demo_state():
    """
    Reset the simulator and create some default demo threads + a semaphore,
    then start the simulation.
    Call this once (e.g. from frontend on page load).
    """
    controller.reset()

    # Choose default model & scheduler BEFORE creating threads
    controller.set_model("MANY_TO_MANY")
    controller.set_scheduler("RR")
    controller.set_quantum(1)

    # Create some demo threads with different burst times & priorities
    controller.add_thread(total_burst=15, priority=1, name="T1-IO-bound")
    controller.add_thread(total_burst=25, priority=2, name="T2-CPU-bound")
    controller.add_thread(total_burst=18, priority=0, name="T3-background")

    # Optional: create a demo semaphore (e.g. shared resource)
    controller.create_semaphore("S1", initial=1)

    # Start simulation
    controller.start()

# Basic state endpoint
@app.route("/api/state", methods=["GET"])
def api_state():
    return jsonify(controller.get_state_snapshot())


# Control endpoints
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


@app.route("/api/reset", methods=["POST"])
def api_reset():
    controller.reset()
    return jsonify({"ok": True})


@app.route("/api/add_thread", methods=["POST"])
def api_add_thread():
    data = request.json or {}
    burst = int(data.get("burst", 10))
    pr = int(data.get("priority", 0))
    name = data.get("name")
    t = controller.add_thread(total_burst=burst, priority=pr, name=name)
    return jsonify({"ok": True, "thread": {"id": t.id, "name": t.name}})


@app.route("/api/set", methods=["POST"])
def api_set():
    data = request.json or {}
    if "model" in data:
        try:
            controller.set_model(data["model"])
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 400
    if "scheduler" in data:
        controller.set_scheduler(data["scheduler"])
    if "quantum" in data:
        controller.set_quantum(int(data["quantum"]))
    return jsonify({"ok": True})

@app.route("/api/init_demo", methods=["POST"])
def api_init_demo():
    """
    Initialize a default demo scenario:
    - Reset everything
    - Create demo threads & semaphore
    - Start simulation
    """
    init_demo_state()
    return jsonify({"ok": True})


# -----------------------------
# Semaphore endpoints
# -----------------------------
@app.route("/api/semaphore/create", methods=["POST"])
def api_sem_create():
    data = request.json or {}
    name = data.get("name")
    initial = int(data.get("initial", 1))
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    s = controller.create_semaphore(name, initial)
    return jsonify({"ok": True, "semaphore": {"name": s.name, "value": s.value}})


@app.route("/api/semaphore/wait", methods=["POST"])
def api_sem_wait():
    data = request.json or {}
    name = data.get("name")
    tid = data.get("thread_id")
    if not name or tid is None:
        return jsonify({"ok": False, "error": "name and thread_id required"}), 400
    result = controller.semaphore_wait(name, tid)
    return jsonify(result)


@app.route("/api/semaphore/signal", methods=["POST"])
def api_sem_signal():
    data = request.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    result = controller.semaphore_signal(name)
    return jsonify(result)


# -----------------------------
# Monitor endpoints
# -----------------------------
@app.route("/api/monitor/create", methods=["POST"])
def api_mon_create():
    data = request.json or {}
    name = data.get("name")
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    m = controller.create_monitor(name)
    return jsonify({"ok": True})


@app.route("/api/monitor/wait", methods=["POST"])
def api_mon_wait():
    data = request.json or {}
    name = data.get("name")
    cond = data.get("cond", "default")
    tid = data.get("thread_id")
    if not name or tid is None:
        return jsonify({"ok": False, "error": "name and thread_id required"}), 400
    result = controller.monitor_wait(name, cond, tid)
    return jsonify(result)


@app.route("/api/monitor/signal", methods=["POST"])
def api_mon_signal():
    data = request.json or {}
    name = data.get("name")
    cond = data.get("cond", "default")
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    result = controller.monitor_signal(name, cond)
    return jsonify(result)


# Serve frontend entry
@app.route("/", methods=["GET"])
def index():
    return send_from_directory(TEMPLATES_DIR, "index.html")


@app.route("/static/<path:path>")
def serve_static(path):
    return send_from_directory(STATIC_DIR, path)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)

