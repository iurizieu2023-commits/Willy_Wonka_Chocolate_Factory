# core/queue.py
import collections
import threading
from typing import Deque, Generic, Optional, TypeVar, List

T = TypeVar("T")


class BoundedQueue(Generic[T]):
    """Thread-safe bounded queue with blocking push/pop."""

    def __init__(self, capacity: int) -> None:
        if capacity <= 0:
            raise ValueError("BoundedQueue capacity must be > 0")
        self.capacity = capacity
        self._queue: Deque[T] = collections.deque()
        self._done = False

        self._mutex = threading.Lock()
        self._not_full = threading.Condition(self._mutex)
        self._not_empty = threading.Condition(self._mutex)

    def push(self, item: T) -> bool:
        with self._mutex:
            self._not_full.wait_for(
                lambda: len(self._queue) < self.capacity or self._done
            )
            if self._done:
                return False
            self._queue.append(item)
            self._not_empty.notify()
            return True

    def pop(self, timeout: Optional[float] = None) -> Optional[T]:
        with self._mutex:
            success = self._not_empty.wait_for(
                lambda: self._queue or self._done, timeout=timeout
            )
            if not success:
                return None  # Timed out
            
            if self._done and not self._queue:
                return None
            
            item = self._queue.popleft()
            self._not_full.notify()
            return item

    def shutdown(self) -> None:
        with self._mutex:
            self._done = True
            self._not_full.notify_all()
            self._not_empty.notify_all()

    def size(self) -> int:
        with self._mutex:
            return len(self._queue)

    def peek_items(self) -> List[T]:
        with self._mutex:
            return list(self._queue)
