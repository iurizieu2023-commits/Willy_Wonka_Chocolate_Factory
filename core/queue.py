# core/queue.py
import collections
import threading
from typing import Deque, Generic, Optional, TypeVar, List

T = TypeVar("T")


class BoundedQueue(Generic[T]):
    """Thread-safe bounded queue with blocking push/pop + optional DB snapshots."""

    def __init__(
        self,
        capacity: int,
        db_queue_id: Optional[int] = None,
        name: Optional[str] = None,
    ) -> None:
        if capacity <= 0:
            raise ValueError("BoundedQueue capacity must be > 0")
        self.capacity = capacity
        self._queue: Deque[T] = collections.deque()
        self._done = False

        self._mutex = threading.Lock()
        self._not_full = threading.Condition(self._mutex)
        self._not_empty = threading.Condition(self._mutex)

        # --- NEW: DB metadata (optional) ---
        self.db_queue_id = db_queue_id
        self.name = name or "Queue"

    # --- NEW: helper to log snapshots into SQLite ---
    def _log_snapshot(self, blocked: int = 0, dropped: int = 0) -> None:
        """
        Write a row into queue_snapshots if this queue is linked to the DB.
        Must be called while holding self._mutex.
        """
        if self.db_queue_id is None:
            return

        try:
            from database.insertions import insert_queue_snapshot
        except Exception:
            # DB is optional – never crash the sim
            return

        try:
            size = len(self._queue)
            insert_queue_snapshot(
                queue_id=self.db_queue_id,
                size=size,
                blocked=int(blocked),
                dropped=int(dropped),
            )
        except Exception:
            # Completely ignore DB errors
            pass

    def push(self, item: T) -> bool:
        with self._mutex:
            self._not_full.wait_for(
                lambda: len(self._queue) < self.capacity or self._done
            )
            if self._done:
                return False
            self._queue.append(item)

            # NEW: log after enqueue
            self._log_snapshot(blocked=0, dropped=0)

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

            # NEW: log after dequeue
            self._log_snapshot(blocked=0, dropped=0)

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
