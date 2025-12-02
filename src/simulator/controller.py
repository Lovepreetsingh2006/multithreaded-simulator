# src/simulator/controller.py
"""
SimulationController:
- Manages simulated threads, kernel threads, schedulers, mapping models
- Runs the ticking loop (background thread)
- Provides functions used by the Flask API (including semaphore & monitor ops)
"""

import threading
import time
from typing import Dict, List, Optional

from .core import (
    SimThread,
    KernelThread,
    ThreadState,
    RoundRobinScheduler,
    FCFSScheduler,
    PriorityScheduler,
    MappingModel,
)
from .sync import SimSemaphore, Monitor

# Default tick interval (seconds)
TICK_INTERVAL = 1


class SimulationController:
    """
    Central manager for the simulator.
    """

    def __init__(self, num_kernel_threads: int = 2,
                 model: MappingModel = MappingModel.MANY_TO_MANY,
                 scheduler_name: str = "RR",
                 quantum: int = 1):

        self.lock = threading.RLock()

        # Thread table: id -> SimThread
        self.threads: Dict[int, SimThread] = {}

        # Kernel threads / cores
        self.kernels: List[KernelThread] = [KernelThread(i) for i in range(num_kernel_threads)]

        # Mapping & scheduling
        self.model = model
        self.quantum = quantum
        self.scheduler = self._make_scheduler(scheduler_name)

        # Simulation state
        self.running = False
        self._tick = 0
        self._runner_thread: Optional[threading.Thread] = None

        # Sync primitives
        self.semaphores: Dict[str, SimSemaphore] = {}
        self.monitors: Dict[str, Monitor] = {}

        # Statistics
        self.stats = {"context_switches": 0, "completed": 0}

    # -----------------------------
    # Internal helpers
    # -----------------------------
    def _make_scheduler(self, name: str):
        name = (name or "RR").upper()
        if name in ("RR", "ROUNDROBIN"):
            return RoundRobinScheduler()
        if name in ("FCFS", "FIFO"):
            return FCFSScheduler()
        if name in ("PRIORITY", "PR"):
            return PriorityScheduler()
        return RoundRobinScheduler()

    # -----------------------------
    # Configuration setters
    # -----------------------------
    def set_scheduler(self, name: str):
        """
        Change scheduler type and re-register all non-terminated, non-blocked threads
        so the new scheduler gets a proper READY queue.
        """
        with self.lock:
            new_sched = self._make_scheduler(name)

            # Re-add all runnable threads to the new scheduler
            for t in self.threads.values():
                if t.state not in (ThreadState.TERMINATED, ThreadState.BLOCKED):
                    new_sched.add(t)

            self.scheduler = new_sched


    def set_model(self, model_name: str):
        with self.lock:
            if isinstance(model_name, str):
                self.model = MappingModel[model_name]
            elif isinstance(model_name, MappingModel):
                self.model = model_name

    def set_quantum(self, q: int):
        with self.lock:
            self.quantum = int(q)

    # -----------------------------
    # Thread lifecycle
    # -----------------------------
    def add_thread(self, total_burst: int = 10, priority: int = 0, name: str = None) -> SimThread:
        with self.lock:
            t = SimThread(total_burst=total_burst, priority=priority, name=name)
            t.state = ThreadState.READY
            self.threads[t.id] = t
            self.scheduler.add(t)
            return t

    def get_thread(self, tid: int) -> Optional[SimThread]:
        return self.threads.get(int(tid))

    # -----------------------------
    # Semaphore & Monitor management
    # -----------------------------
    def create_semaphore(self, name: str, initial: int = 1) -> SimSemaphore:
        with self.lock:
            s = SimSemaphore(initial, name=name)
            self.semaphores[name] = s
            return s

    def get_semaphore(self, name: str) -> Optional[SimSemaphore]:
        return self.semaphores.get(name)

    def create_monitor(self, name: str) -> Monitor:
        with self.lock:
            m = Monitor()
            self.monitors[name] = m
            return m

    def get_monitor(self, name: str) -> Optional[Monitor]:
        return self.monitors.get(name)

    # -----------------------------
    # Cooperative blocking operations
    # -----------------------------

    def semaphore_wait(self, sem_name: str, thread_id: int) -> Dict:
        """
        Attempt P() on semaphore for given thread.
        If the semaphore causes blocking, mark thread BLOCKED and remove from scheduler.
        Returns a dict: {"acquired": bool, "blocked": bool}
        """
        with self.lock:
            sem = self.semaphores.get(sem_name)
            t = self.threads.get(int(thread_id))
            if sem is None:
                return {"ok": False, "error": f"Semaphore '{sem_name}' not found."}
            if t is None:
                return {"ok": False, "error": f"Thread id {thread_id} not found."}

            acquired = sem.P(t)
            if not acquired:
                # block the thread: remove from scheduler queue, set state
                t.state = ThreadState.BLOCKED
                try:
                    self.scheduler.remove(t)
                except Exception:
                    pass
                # If the thread was assigned to a kernel, release it
                for k in self.kernels:
                    if k.current_thread is t:
                        k.release()
                return {"ok": True, "acquired": False, "blocked": True}
            else:
                return {"ok": True, "acquired": True, "blocked": False}

    def semaphore_signal(self, sem_name: str) -> Dict:
        """
        Perform V() on semaphore; if an unblocked thread returned by V(), set it to READY and re-add to scheduler.
        """
        with self.lock:
            sem = self.semaphores.get(sem_name)
            if sem is None:
                return {"ok": False, "error": f"Semaphore '{sem_name}' not found."}
            unblocked = sem.V()
            if unblocked is not None:
                # set unblocked thread to READY and add back to scheduler
                unblocked.state = ThreadState.READY
                self.scheduler.add(unblocked)
                return {"ok": True, "unblocked": unblocked.id}
            return {"ok": True, "unblocked": None}

    # Monitor primitives (simple)
    def monitor_wait(self, monitor_name: str, cond_name: str, thread_id: int) -> Dict:
        with self.lock:
            mon = self.monitors.get(monitor_name)
            t = self.threads.get(int(thread_id))
            if mon is None:
                return {"ok": False, "error": f"Monitor '{monitor_name}' not found."}
            if t is None:
                return {"ok": False, "error": f"Thread id {thread_id} not found."}
            # caller is expected to release monitor lock; here we just enqueue
            t.state = ThreadState.BLOCKED
            mon.wait(cond_name, t)
            try:
                self.scheduler.remove(t)
            except Exception:
                pass
            # release assignment if any
            for k in self.kernels:
                if k.current_thread is t:
                    k.release()
            return {"ok": True, "blocked": t.id}

    def monitor_signal(self, monitor_name: str, cond_name: str) -> Dict:
        with self.lock:
            mon = self.monitors.get(monitor_name)
            if mon is None:
                return {"ok": False, "error": f"Monitor '{monitor_name}' not found."}
            th = mon.signal(cond_name)
            if th:
                th.state = ThreadState.READY
                self.scheduler.add(th)
                return {"ok": True, "unblocked": th.id}
            return {"ok": True, "unblocked": None}

    def monitor_broadcast(self, monitor_name: str, cond_name: str) -> Dict:
        with self.lock:
            mon = self.monitors.get(monitor_name)
            if mon is None:
                return {"ok": False, "error": f"Monitor '{monitor_name}' not found."}
            lst = mon.broadcast(cond_name)
            for th in lst:
                th.state = ThreadState.READY
                self.scheduler.add(th)
            return {"ok": True, "unblocked": [t.id for t in lst]}

    # -----------------------------
    # Snapshot for frontend
    # -----------------------------
    def get_state_snapshot(self) -> Dict:
        with self.lock:
            threads = [
                {
                    "id": t.id,
                    "name": t.name,
                    "state": t.state.value,
                    "remaining": t.remaining,
                    "priority": t.priority,
                    "mapped_kernel": t.mapped_kernel,
                }
                for t in sorted(self.threads.values(), key=lambda x: x.id)
            ]
            kernels = [
                {
                    "id": k.id,
                    "current_thread": k.current_thread.id if k.current_thread else None,
                }
                for k in self.kernels
            ]
            sems = {name: {"value": s.value, "blocked": [th.id for th in s.peek_blocked()]} for name, s in self.semaphores.items()}
            mons = {name: {"conds": {}} for name in self.monitors.keys()}
            stats = dict(self.stats)
            return {
                "tick": self._tick,
                "threads": threads,
                "kernels": kernels,
                "semaphores": sems,
                "monitors": mons,
                "model": self.model.value,
                "quantum": self.quantum,
                "stats": stats,
            }

    # -----------------------------
    # Tick / Run loop
    # -----------------------------
    def _assign_thread_to_kernel(self, thread: SimThread) -> KernelThread:
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
                if k.current_thread is None or k.current_thread.state in (ThreadState.TERMINATED, ThreadState.BLOCKED):
                    k.assign(thread)
                    return k
            k = self.kernels[0]
            k.assign(thread)
            return k

    def _run_tick(self):
            with self.lock:
                self._tick += 1

            for k in self.kernels:

                # If kernel is empty or has a non-runnable thread, assign a new one
                if k.current_thread is None or k.current_thread.state in (
                    ThreadState.TERMINATED,
                    ThreadState.BLOCKED,
                ):
                    nxt = self.scheduler.next()
                    if nxt is None:
                        k.release()
                        continue
                    if nxt.state == ThreadState.TERMINATED:
                        continue

                    self.stats["context_switches"] += 1
                    nxt.state = ThreadState.RUNNING
                    k.assign(nxt)

                # If after this we still have no thread assigned, skip
                if k.current_thread is None:
                    continue

                # Run one quantum on the assigned thread
                used = k.current_thread.run_slice(self.quantum)

                # If the thread finished during this tick, free the core
                if k.current_thread.state == ThreadState.TERMINATED:
                    self.stats["completed"] += 1
                    k.release()
                    # No requeue; finished is done
                    continue

                # IMPORTANT: we do NOT requeue + release here.
                # The thread stays bound to this core and in RUNNING state
                # until it finishes or is blocked. This makes the core visibly busy
                # in the frontend between ticks.




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

    # -----------------------------
    # Utility: reset (handy for demos)
    # -----------------------------
    def reset(self):
        with self.lock:
            self.threads.clear()
            for k in self.kernels:
                k.release()
            self.semaphores.clear()
            self.monitors.clear()
            self._tick = 0
            self.stats = {"context_switches": 0, "completed": 0}
            # also reset scheduler
            self.scheduler = self._make_scheduler("RR")

