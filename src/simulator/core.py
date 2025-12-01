# src/simulator/core.py

"""
Core simulator classes:
- SimThread: simulated thread
- KernelThread: simulated CPU/core
- Schedulers: Round Robin, FCFS, Priority
- Mapping models: Many-to-One, One-to-One, Many-to-Many
"""

import enum
import itertools
import threading
from collections import deque
from typing import List, Optional


# -----------------------------
# ENUMS & ID GENERATORS
# -----------------------------

class ThreadState(enum.Enum):
    NEW = "NEW"
    READY = "READY"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    TERMINATED = "TERMINATED"


class MappingModel(enum.Enum):
    MANY_TO_ONE = "MANY_TO_ONE"
    ONE_TO_ONE = "ONE_TO_ONE"
    MANY_TO_MANY = "MANY_TO_MANY"


_next_thread_id = itertools.count(1)


# -----------------------------
# SIMULATED THREAD
# -----------------------------

class SimThread:
    def __init__(self, total_burst: int = 10, priority: int = 0, name: Optional[str] = None):
        self.id = next(_next_thread_id)
        self.name = name or f"T{self.id}"
        self.total_burst = total_burst
        self.remaining = total_burst
        self.priority = priority
        self.state = ThreadState.NEW
        self.mapped_kernel = None
        self.lock = threading.Lock()

    def is_done(self):
        return self.remaining <= 0

    def run_slice(self, quantum=1):
        with self.lock:
            if self.state in (ThreadState.BLOCKED, ThreadState.TERMINATED):
                return 0

            to_run = min(self.remaining, quantum)
            self.remaining -= to_run

            if self.remaining <= 0:
                self.state = ThreadState.TERMINATED
            else:
                self.state = ThreadState.READY

            return to_run

    def __repr__(self):
        return f"<SimThread {self.name} id={self.id} state={self.state.name} rem={self.remaining} pr={self.priority}>"



# -----------------------------
# SIMULATED KERNEL THREAD / CPU CORE
# -----------------------------

class KernelThread:
    def __init__(self, kid: int):
        self.id = kid
        self.current_thread: Optional[SimThread] = None
        self.lock = threading.Lock()

    def assign(self, thread: SimThread):
        with self.lock:
            self.current_thread = thread
            thread.mapped_kernel = self.id

    def release(self):
        with self.lock:
            if self.current_thread:
                self.current_thread.mapped_kernel = None
            self.current_thread = None

    def __repr__(self):
        return f"<KernelThread id={self.id} running={self.current_thread}>"



# -----------------------------
# SCHEDULERS
# -----------------------------

class SchedulerBase:
    def add(self, thread: SimThread):
        raise NotImplementedError()

    def remove(self, thread: SimThread):
        raise NotImplementedError()

    def next(self) -> Optional[SimThread]:
        raise NotImplementedError()

    def peek_queue(self) -> List[SimThread]:
        raise NotImplementedError()



# ROUND ROBIN
class RoundRobinScheduler(SchedulerBase):
    def __init__(self):
        self.queue = deque()
        self.lock = threading.Lock()

    def add(self, thread: SimThread):
        with self.lock:
            if thread.state != ThreadState.TERMINATED and thread not in self.queue:
                thread.state = ThreadState.READY
                self.queue.append(thread)

    def remove(self, thread: SimThread):
        with self.lock:
            try: self.queue.remove(thread)
            except ValueError: pass

    def next(self):
        with self.lock:
            if not self.queue:
                return None
            t = self.queue.popleft()
            return t if t.state != ThreadState.TERMINATED else self.next()

    def peek_queue(self):
        with self.lock:
            return list(self.queue)



# FCFS
class FCFSScheduler(SchedulerBase):
    def __init__(self):
        self.queue = deque()
        self.lock = threading.Lock()

    def add(self, thread: SimThread):
        with self.lock:
            if thread.state != ThreadState.TERMINATED and thread not in self.queue:
                thread.state = ThreadState.READY
                self.queue.append(thread)

    def remove(self, thread: SimThread):
        with self.lock:
            try: self.queue.remove(thread)
            except ValueError: pass

    def next(self):
        with self.lock:
            while self.queue:
                t = self.queue[0]
                if t.state == ThreadState.TERMINATED:
                    self.queue.popleft()
                    continue
                return t
            return None

    def peek_queue(self):
        with self.lock:
            return list(self.queue)



# PRIORITY
class PriorityScheduler(SchedulerBase):
    def __init__(self):
        self.lock = threading.Lock()
        self.heap = []

    def add(self, thread: SimThread):
        with self.lock:
            if thread.state != ThreadState.TERMINATED and thread not in self.heap:
                thread.state = ThreadState.READY
                self.heap.append(thread)

    def remove(self, thread: SimThread):
        with self.lock:
            try: self.heap.remove(thread)
            except ValueError: pass

    def next(self):
        with self.lock:
            valid = [t for t in self.heap if t.state != ThreadState.TERMINATED]
            if not valid:
                return None
            sel = max(valid, key=lambda t: (t.priority, -t.id))
            self.heap.remove(sel)
            return sel

    def peek_queue(self):
        with self.lock:
            return list(self.heap)
