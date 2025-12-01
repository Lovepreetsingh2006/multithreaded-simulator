# src/simulator/sync.py

"""
Synchronization primitives for the simulator:
- SimSemaphore: counting/binary semaphore with FIFO queue
- Monitor: simulated monitor with condition variables
"""

import threading
from collections import deque
from typing import Deque, Optional


# -----------------------------
# SEMAPHORE
# -----------------------------

class SimSemaphore:
    def __init__(self, initial: int = 1, name: Optional[str] = None):
        self.value = initial
        self.lock = threading.Lock()
        self.blocked: Deque = deque()
        self.name = name or f"sem_{id(self)}"

    def P(self, thread):
        """
        WAIT operation (P):
        - If semaphore value > 0 → decrement and continue
        - Else → block thread (thread must be removed from scheduler externally)
        Returns:
            True  -> acquired
            False -> thread blocked
        """
        with self.lock:
            self.value -= 1

            if self.value < 0:
                # Need to block
                self.blocked.append(thread)
                return False

            return True

    def V(self):
        """
        SIGNAL operation (V):
        - Increment value
        - If blocked threads exist → unblock one
        Returns:
            The unblocked thread object, or None
        """
        with self.lock:
            self.value += 1

            if self.blocked:
                return self.blocked.popleft()

            return None

    def peek_blocked(self):
        """Return list of blocked thread objects (for visualization)"""
        with self.lock:
            return list(self.blocked)



# -----------------------------
# MONITOR (simulated)
# -----------------------------

class Monitor:
    """
    Simple simulated monitor wrapper.
    - Has 1 lock (not OS mutex, just a simulation lock)
    - Condition variables stored in a dictionary (name -> queue)
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.conditions = {}  # name: deque of threads

    def _queue(self, name):
        """Return condition queue, create if needed"""
        if name not in self.conditions:
            self.conditions[name] = deque()
        return self.conditions[name]

    def wait(self, name: str, thread):
        """
        Put 'thread' into the condition queue.
        (Caller must set thread.state = BLOCKED outside.)
        """
        q = self._queue(name)
        q.append(thread)

    def signal(self, name: str):
        """
        Wake one waiting thread.
        Returns the thread to unblock, or None.
        """
        q = self._queue(name)
        if q:
            return q.popleft()
        return None

    def broadcast(self, name: str):
        """
        Wake all waiting threads.
        Returns list of woken threads.
        """
        q = self._queue(name)
        lst = list(q)
        q.clear()
        return lst

    def peek(self, name: str):
        """Return list of waiting threads for visualization"""
        return list(self._queue(name))
