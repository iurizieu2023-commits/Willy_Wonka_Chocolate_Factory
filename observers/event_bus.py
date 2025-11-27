# observers/event_bus.py

from typing import Callable, Dict, List, Any


class EventBus:
    """
    Simple Observer pattern implementation.
    - subscribe(event_type, callback)
    - subscribe_all(callback)
    - publish(event_type, data)
    """

    def __init__(self) -> None:
        self.subscribers: Dict[str, List[Callable[[str, dict], None]]] = {}
        self.subscribers_all: List[Callable[[str, dict], None]] = []

    # Subscribe to only one event type
    def subscribe(self, event_type: str, callback: Callable[[str, dict], None]) -> None:
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(callback)

    # Subscribe to ALL event types
    def subscribe_all(self, callback: Callable[[str, dict], None]) -> None:
        self.subscribers_all.append(callback)

    # Publish event to listeners
    def publish(self, event_type: str, data: dict) -> None:
        data = data.copy()
        # Note: Do NOT overwrite data["type"] here - event generators set it correctly!
        # The event_type parameter is used for routing, not as event metadata

        # notify event-specific listeners
        for cb in self.subscribers.get(event_type, []):
            cb(event_type, data)

        # notify universal listeners
        for cb in self.subscribers_all:
            cb(event_type, data)
