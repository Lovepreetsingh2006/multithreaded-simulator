# src/simulator/controller.py

"""
SimulationController:
- Manages simulated threads, kernel threads, schedulers, mapping models
- Runs the ticking loop (background thread)
- Provides functions used by the Flask API
"""

import threading
import time
from typing import Dict, List

from .core import (
    SimThread,
    KernelThread,
    ThreadState,
    RoundRobinScheduler,
    FCFSScheduler,
    PriorityScheduler,
    MappingModel,
)
from .sync import SimSemaphore


# Speed of simulation: 1 tick = 0.2 sec
TICK_INTERVAL = 0.2


class SimulationController:
    """
    Central manager for the simulator.
    """

    def __init__(self, num_kernel_threads=2, model=MappingModel.MANY_TO_MANY,
                 scheduler_name="RR", quantum=1):

        self.lock = threading.RLock()

        # Thread table
        self.threads: Dict[int, SimThread] = {}

        # CPU cores
        self.kernels: List[KernelThread] = [
            KernelThread(i) for i in range(num_kernel_threads)
        ]

        # Scheduling & mapping
        self.model = model
        self.quantum = quantum
        self.scheduler = self._make_scheduler(scheduler_name)

        # Simulation state
        self.running = False
        self._tick = 0
        self._runner_thread = None

        # Synchronization objects
        self.semaphores: Dict[str, SimSemaphore] = {}

        # Statistics
        self.stats = {
            "context_switches": 0,
            "completed": 0
        }

    # -----------------------------
    # INTERNAL HELPERS
    # -----------------------------

    def _make_scheduler(self, name):
        name = name.upper()
        if name in ("RR", "ROUNDROBIN"):
            return RoundRobinScheduler()
        if name in ("FCFS", "FIFO"):
            return FCFSScheduler()
        if name in ("PRIORITY", "PR"):
            return PriorityScheduler()
        return RoundRobinScheduler()

    # -----------------------------
    # CONTROLLED SETTINGS
    # -----------------------------

    def set_scheduler(self, name):
        with self.lock:
            self.scheduler = self._make_scheduler(name)

    def set_model(self, model_name: str):
        with self.lock:
            self.model = MappingModel[model_name]

    def set_quantum(self, q: int):
        with self.lock:
            self.quantum = q

    # -----------------------------
    # THREAD MANAGEMENT
    # -----------------------------

    def add_thread(self, total_burst=10, priority=0, name=None):
        with self.lock:
            t = SimThread(total_burst=total_burst, priority=priority, name=name)
            t.state = ThreadState.READY
            self.threads[t.id] = t
            self.scheduler.add(t)
            return t

    # -----------------------------
    # SEMAPHORE MANAGEMENT
    # -----------------------------

    def create_semaphore(self, name: str, initial=1):
        with self.lock:
            s = SimSemaphore(initial, name=name)
            self.semaphores[name] = s
            return s

    # -----------------------------
    # STATE SNAPSHOT (for frontend)
    # -----------------------------

    def get_state_snapshot(self):
        """
        Return JSON-serializable snapshot of entire simulation state.
        """

        with self.lock:
            threads_list = []
            for t in self.threads.values():
                threads_list.append({
                    "id": t.id,
                    "name": t.name,
                    "state": t.state.value,
                    "remaining": t.remaining,
                    "priority": t.priority,
                    "mapped_kernel": t.mapped_kernel
                })

            kernels_list = []
            for k in self.kernels:
                kernels_list.append({
                    "id": k.id,
                    "current_thread": k.current_thread.id if k.current_thread else None
                })

            sems = {}
            for name, sem in self.semaphores.items():
                sems[name] = {
                    "value": sem.value,
                    "blocked": [t.id for t in sem.peek_blocked()]
                }

            return {
                "tick": self._tick,
                "threads": threads_list,
                "kernels": kernels_list,
                "semaphores": sems,
                "model": self.model.value,
                "quantum": self.quantum,
                "stats": dict(self.stats)
            }

    # -----------------------------
    # MAIN TICK FUNCTION
    # -----------------------------

    def _assign_thread_to_kernel(self, thread):
        """
        Mapping model logic.
        """

        if self.model == MappingModel.MANY_TO_ONE:
            k = self.kernels[0]
            k.assign(thread)
            return k

        elif self.model == MappingModel.ONE_TO_ONE:
            idx = (thread.id - 1) % len(self.kernels)
            k = self.kernels[idx]
            k.assign(thread)
            return k

        else:  # MANY_TO_MANY
            for k in self.kernels:
                if k.current_thread is None or k.current_thread.state == ThreadState.TERMINATED:
                    k.assign(thread)
                    return k
            # fallback: assign to kernel 0
            k = self.kernels[0]
            k.assign(thread)
            return k

    def _run_tick(self):
        with self.lock:
            self._tick += 1

            # For each kernel
            for core in self.kernels:

                # If core has no running thread, get one
                if (core.current_thread is None
                        or core.current_thread.state in (ThreadState.TERMINATED, ThreadState.BLOCKED)):

                    nxt = self.scheduler.next()
                    if nxt is None:
                        continue

                    if nxt.state == ThreadState.TERMINATED:
                        continue

                    self.stats["context_switches"] += 1
                    nxt.state = ThreadState.RUNNING
                    core.assign(nxt)

                # Run assigned thread
                if core.current_thread and core.current_thread.state == ThreadState.RUNNING:
                    used = core.current_thread.run_slice(self.quantum)

                    if core.current_thread.state == ThreadState.TERMINATED:
                        self.stats["completed"] += 1
                        core.release()

                    else:
                        # Put back to scheduler
                        self.scheduler.add(core.current_thread)
                        core.release()

    # -----------------------------
    # RUNNING LOOP
    # -----------------------------

    def start(self):
        with self.lock:
            if self.running:
                return
            self.running = True
            self._runner_thread = threading.Thread(target=self._run_loop, daemon=True)
            self._runner_thread.start()

    def _run_loop(self):
        while True:
            with self.lock:
                if not self.running:
                    break
            self._run_tick()
            time.sleep(TICK_INTERVAL)

    def pause(self):
        with self.lock:
            self.running = False

    def step(self):
        with self.lock:
            self._run_tick()
