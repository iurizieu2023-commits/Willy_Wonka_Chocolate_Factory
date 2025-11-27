# dashboard/dashboard.py

import threading
import time
from typing import Dict, List
from utils.colors import Color


class Dashboard(threading.Thread):
    """
    Real-time Dashboard for all factory activity.
    Shows:
        • Station statuses
        • Queue usage bars
        • Item processing + boxing
        • Supervisor metrics (latency, golden ratio, workers)
        • Worker added/removed
        • Global events (robbery, VIP, breakdowns, etc.)
    """

    MAX_EVENTS = 8

    def __init__(self, stations: List[threading.Thread],
                 queues: Dict[str, object],
                 event_bus):

        super().__init__(daemon=True)
        self.stations = stations
        self.queues = queues
        self.event_bus = event_bus

        self.running = True
        self.start_time = time.time()
        self.events_log = []
        self.total_boxed = 0

        # Subscribe to relevant events
        event_bus.subscribe("item_created", self._handle_item_created)
        event_bus.subscribe("item_processed", self._handle_item_processed)
        event_bus.subscribe("filling_done", self._handle_filling_done)
        event_bus.subscribe("item_boxed", self._handle_item_boxed)

        event_bus.subscribe("queue_update", self._handle_queue_update)
        event_bus.subscribe("queue_closed", self._handle_generic)

        event_bus.subscribe("worker_added", self._handle_generic)
        event_bus.subscribe("worker_removed", self._handle_generic)
        event_bus.subscribe("worker_event", self._handle_generic)

        event_bus.subscribe("station_paused", self._handle_generic)
        event_bus.subscribe("station_resumed", self._handle_generic)
        event_bus.subscribe("station_fault", self._handle_generic)
        event_bus.subscribe("station_shutdown", self._handle_generic)

        event_bus.subscribe("supervisor_alert", self._handle_generic)
        event_bus.subscribe("supervisor_metrics", self._handle_metrics)

        event_bus.subscribe("global_event", self._handle_global_event)

    # ---------------------------------------------------------
    # Event handlers
    # ---------------------------------------------------------

    def _push_event(self, ev):
        self.events_log.append(ev)
        if len(self.events_log) > self.MAX_EVENTS:
            self.events_log.pop(0)

    def _handle_item_created(self, event_type, data):
        self._push_event({"type": "item_created", **data})

    def _handle_item_processed(self, event_type, data):
        self._push_event({"type": "item_processed", **data})

    def _handle_filling_done(self, event_type, data):
        self._push_event({"type": "filling_done", **data})

    def _handle_item_boxed(self, event_type, data):
        self.total_boxed += 1
        self._push_event({"type": "item_boxed", **data})

    def _handle_queue_update(self, event_type, data):
        self._push_event({"type": "queue_update", **data})

    def _handle_generic(self, event_type, data):
        if data:
            self._push_event(data)

    def _handle_metrics(self, event_type, data):
        self._push_event({"type": "metrics", **data})

    def _handle_global_event(self, event_type, data):
        if data:
            self._push_event({"type": "global_event", **data})

    # ---------------------------------------------------------
    # Utility
    # ---------------------------------------------------------

    def _bar(self, size, cap):
        size = int(size)
        cap = int(cap)
        fill = "█" * size
        empty = "░" * (cap - size)
        return f"{fill}{empty}"

    # ---------------------------------------------------------
    # Main loop: dashboard display
    # ---------------------------------------------------------

    def run(self):
        while self.running:
            uptime = time.time() - self.start_time

            print("\n" + Color.BOLD + "=" * 80 + Color.RESET)
            print(f"{Color.BOLD}🍫 WONKA PRODUCTION DASHBOARD {Color.RESET}")
            print(f"Uptime: {uptime:.1f}s | Total Boxed: {self.total_boxed}")
            print("=" * 80)

            # ---------------- Stations ----------------
            print(f"\n{Color.BOLD}👷 STATION STATUS:{Color.RESET}")
            for st in self.stations:
                activity = getattr(st, "current_activity", "idle")
                print(f"  {st.name:22} → {activity}")

            # ---------------- Queues ----------------
            print(f"\n{Color.BOLD}📦 CONVEYOR BELTS:{Color.RESET}")
            for name, q in self.queues.items():
                size = q.size()
                bar = self._bar(size, q.capacity)
                print(f"  {name:15} {bar}  {size}/{q.capacity}")

            # ---------------- Events ----------------
            print(f"\n{Color.BOLD}📜 EVENT LOG (latest {self.MAX_EVENTS}):{Color.RESET}")
            for e in self.events_log:
                et = e.get("type")

                if et == "item_created":
                    print(f"  🍪 Created Item {e['item_id']} at {e['station']}")

                elif et == "item_processed":
                    print(f"  🔧 Processed {e['item_id']} at {e['station']}")

                elif et == "filling_done":
                    print(f"  🥤 Filled {e['item_id']} with {e['filling']}")

                elif et == "item_boxed":
                    print(f"  📦 Boxed Item {e['item_id']} (golden={e['golden']})")

                elif et == "queue_update":
                    print(f"  🔄 Queue {e['name']} → size={e['size']}")

                elif et == "metrics":
                    print(f"  📊 Supervisor metrics → boxed={e['total_boxed']} latency={e['avg_latency']:.2f}")

                elif et == "global_event":
                    print(f"  🌎 {e['msg']}")

                else:
                    print(f"  • {e}")

            time.sleep(1.0)

    def stop(self):
        self.running = False
