# core/station.py
import threading
import time
import random
from typing import Optional, List

from core.queue import BoundedQueue
from core.item import Item
from observers.event_bus import EventBus
from utils.colors import Color


# ============================================================
# BASE STATION (Template Method Pattern)
# ============================================================
class BaseStation(threading.Thread):
    """
    Template Method pattern:
        run()
          -> _take_item()
          -> process_item()   (overridden by subclasses)
          -> _send_item()
    """

    def __init__(
        self,
        name: str,
        in_queue: BoundedQueue[Item],
        out_queue: BoundedQueue[Item],
        event_bus: EventBus,
        factory_name: str = "Unknown",
        initial_workers: int = 1,
        max_workers: int = 3,  # Phase 11: Worker scaling limit - Changed default to 3
    ) -> None:
        super().__init__(name=name)
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.event_bus = event_bus
        self.factory_name = factory_name
        self.initial_workers = initial_workers
        self.max_workers = max_workers  # Maximum workers allowed
        self.current_activity = f"{Color.BLUE}Idle{Color.RESET}"

        # NEW: fault support
        self.faulted = False
        self.fault_until = 0

        # IMPORTANT: daemon → process exits when main thread finishes
        self.daemon = True

    # ---- Primitive operation to override ----
    def process_item(self, item: Item) -> Optional[Item]:
        """Default implementation (safe fallback)."""
        self.current_activity = f"{Color.GREEN}{self.name}...{Color.RESET}"
        time.sleep(random.uniform(0.1, 0.3))
        return item

    # ---- Template Method (DO NOT OVERRIDE) ----
    def run(self) -> None:
        while True:
            # NEW — fault freeze
            if self.faulted:
                self.current_activity = f"{Color.RED}Faulted{Color.RESET}"
                time.sleep(0.2)
                continue

            self.current_activity = f"{Color.BLUE}Waiting...{Color.RESET}"
            item = self.in_queue.pop()

            if item is None:
                # Upstream finished
                self.current_activity = f"{Color.YELLOW}Shutdown{Color.RESET}"
                if self.out_queue:
                    self.out_queue.shutdown()
                self.event_bus.publish(
                    "station_shutdown",
                    {"station": self.name, "factory": self.factory_name},
                )
                break

            # Process the item (delegated to subclass)
            try:
                start = time.time()
                processed_item = self.process_item(item)
                duration = time.time() - start

                # Note: BaseStation does not track utilization in this version

                if processed_item:
                    # Push to next queue
                    if self.out_queue:
                        self.current_activity = f"{Color.RED}Blocked?{Color.RESET}"
                        ok = self.out_queue.push(processed_item)
                        if not ok:
                            self.current_activity = f"{Color.YELLOW}Shutdown{Color.RESET}"
                            break

                    # Publish event
                    self.current_activity = f"{Color.GREEN}Done{Color.RESET}"
                    self.event_bus.publish(
                        "item_processed",
                        {
                            "station": self.name,
                            "factory": self.factory_name,
                            "item_id": processed_item.id,
                            "latency_stage": duration,
                            "golden": processed_item.is_golden,
                        },
                    )

            except Exception as e:
                print(f"{Color.RED}CRASH in {self.name} worker: {e}{Color.RESET}")
                import traceback
                traceback.print_exc()

        self.current_activity = f"{Color.GREEN}Finished{Color.RESET}"

# ============================================================
# SCALABLE STATION (Phase 2: Worker Scaling + Stress Tracking)
# ============================================================
class ScalableStation(BaseStation):
    """
    Extends BaseStation with:
    - Multiple worker threads
    - Dynamic add/remove workers
    - Stress tracking
    - Fault (breakdown) handling
    """

    def __init__(
        self,
        name: str,
        in_queue: BoundedQueue[Item],
        out_queue: Optional[BoundedQueue[Item]],
        event_bus: EventBus,
        factory_name: str = "Unknown",
        max_workers: int = 5,
    ) -> None:

        # We do *not* call BaseStation.__init__ because ScalableStation
        # manages multiple workers manually.
        threading.Thread.__init__(self, name=name)

        self.in_queue = in_queue
        self.out_queue = out_queue
        self.event_bus = event_bus
        self.factory_name = factory_name
        self.max_workers = max_workers

        self.current_activity = f"{Color.BLUE}Idle{Color.RESET}"
        self.daemon = False

        # Worker pool
        self.workers: List[threading.Thread] = []
        self.worker_stop_events: List[threading.Event] = []
        self._worker_id_counter = 1
        self._running = True
        self._lock = threading.Lock()

        # Metrics
        self.utilization = 0.0
        self.stress_score = 0.0
        self.is_faulted = False          # <- MATCHED FOR DASHBOARD
        self.breakdown_until = 0.0       # <- Freeze until timestamp
        self._stress_lock = threading.Lock()

        # Utilization metrics
        self._total_processing_time = 0.0
        self._total_idle_time = 0.0
        self._items_processed = 0

    # ------------------------------------------------------------
    # 🔧 BREAKDOWN / FAULT API (Supervisor uses this)
    # ------------------------------------------------------------
    def trigger_breakdown(self, duration: float) -> None:
        """Called by Supervisor when EventEngine emits machine_breakdown."""
        self.is_faulted = True
        self.breakdown_until = time.time() + float(duration)

        self.event_bus.publish(
            "station_faulted",
            {
                "station": self.name,
                "factory": self.factory_name,
                "duration": float(duration),
            },
        )

    # ------------------------------------------------------------
    # Worker management
    # ------------------------------------------------------------
    def start_workers(self, n: int = 1) -> None:
        with self._lock:
            for _ in range(n):
                self._spawn_worker()

    def add_worker(self) -> bool:
        with self._lock:
            if not self._running:
                return False
            if len(self.workers) >= self.max_workers:
                return False

            self._spawn_worker()
            self.event_bus.publish(
                "worker_added",
                {
                    "station": self.name,
                    "factory": self.factory_name,
                    "count": len(self.workers),
                    "max": self.max_workers,
                },
            )
            return True

    def remove_worker(self) -> None:
        with self._lock:
            if len(self.workers) <= 1:
                return
            worker = self.workers.pop()
            self.event_bus.publish(
                "worker_removed",
                {
                    "station": self.name,
                    "factory": self.factory_name,
                    "total_workers": len(self.workers),
                },
            )

    def _spawn_worker(self) -> None:
        worker_id = self._worker_id_counter
        self._worker_id_counter += 1

        stop_event = threading.Event()
        worker = threading.Thread(
            target=self._worker_loop,
            args=(stop_event,),
            name=f"{self.name}-Worker-{worker_id}",
            daemon=True,
        )
        self.workers.append(worker)
        self.worker_stop_events.append(stop_event)
        worker.start()

    # ------------------------------------------------------------
    # Worker loop (where the fault freeze happens)
    # ------------------------------------------------------------
    def _worker_loop(self, stop_event: threading.Event) -> None:
        """Worker loop with fault freeze and repair logic."""

        while not stop_event.is_set():

            # --------------------------------------------------
            # 1. FAULT FREEZE
            # --------------------------------------------------
            if self.is_faulted:
                # Still in breakdown window?
                if time.time() < self.breakdown_until:
                    self.current_activity = f"{Color.RED}FAULTED – REPAIRING...{Color.RESET}"
                    time.sleep(0.3)
                    continue

                # Breakdown over -> auto repair
                self.is_faulted = False
                self.breakdown_until = 0
                self.event_bus.publish(
                    "station_repaired",
                    {"station": self.name, "factory": self.factory_name},
                )

            # --------------------------------------------------
            # 2. TRY TO GET ITEM
            # --------------------------------------------------
            item = self.in_queue.pop(timeout=0.1)

            if item is None:
                # Empty or shutdown
                if self.in_queue._done:
                    break
                self.current_activity = f"{Color.BLUE}Waiting...{Color.RESET}"
                continue

            # --------------------------------------------------
            # 3. PROCESS ITEM
            # --------------------------------------------------
            start = time.time()
            processed = self.process_item(item)
            duration = time.time() - start

            with self._stress_lock:
                self._items_processed += 1
                self._total_processing_time += duration

            # --------------------------------------------------
            # 4. SEND DOWNSTREAM
            # --------------------------------------------------
            if processed is not None and self.out_queue is not None:
                self.current_activity = f"{Color.RED}Blocked?{Color.RESET}"
                ok = self.out_queue.push(processed)
                if not ok:
                    self.current_activity = f"{Color.YELLOW}Shutdown{Color.RESET}"
                    break

            # --------------------------------------------------
            # 5. EMIT "ITEM PROCESSED"
            # --------------------------------------------------
            self.current_activity = f"{Color.GREEN}Done{Color.RESET}"
            self.event_bus.publish(
                "item_processed",
                {
                    "station": self.name,
                    "factory": self.factory_name,
                    "item_id": item.id,
                    "latency_stage": duration,
                    "golden": item.is_golden,
                },
            )

            # Update stress
            self.update_stress(duration)

        self.current_activity = f"{Color.GREEN}Finished{Color.RESET}"

    # ------------------------------------------------------------
    # Stress tracking
    # ------------------------------------------------------------
    def update_stress(self, processing_time: float) -> None:
        with self._stress_lock:
            queue_size = self.in_queue.size()
            queue_capacity = self.in_queue.capacity
            queue_stress = queue_size / queue_capacity if queue_capacity > 0 else 0

            latency_stress = min(processing_time / 1.0, 1.0)
            new_stress = 0.6 * queue_stress + 0.4 * latency_stress

            alpha = 0.3
            self.stress_score = alpha * new_stress + (1 - alpha) * self.stress_score

            # Stress-based auto-fault
            FAULT_THRESHOLD = 0.8
            if self.stress_score > FAULT_THRESHOLD and not self.is_faulted:
                self.is_faulted = True
                self.breakdown_until = time.time() + 5  # small cooldown fault
                self.event_bus.publish(
                    "station_fault",
                    {
                        "station": self.name,
                        "factory": self.factory_name,
                        "stress_score": self.stress_score,
                    },
                )

    # ------------------------------------------------------------
    def repair(self) -> None:
        """Manual repair call."""
        with self._stress_lock:
            self.is_faulted = False
            self.breakdown_until = 0
            self.stress_score *= 0.5
            self.event_bus.publish(
                "station_repaired",
                {"station": self.name, "factory": self.factory_name},
            )

    # ------------------------------------------------------------
    def get_utilization(self) -> float:
        with self._stress_lock:
            total_time = self._total_processing_time + self._total_idle_time
            if total_time == 0:
                return 0.0
            return self._total_processing_time / total_time

    def wait_until_done(self) -> None:
        for worker in self.workers:
            if worker.is_alive():
                worker.join()

    def stop(self) -> None:
        self._running = False
# ============================================================
# CRUSHING STATION (Producer - Demand-Driven)
# ============================================================
class CrushingStation(threading.Thread):
    """First stage — produces new items based on factory backlog (demand-driven)."""

    def __init__(
        self,
        name: str,
        out_queue: BoundedQueue[Item],
        num_items: int = None,  # Optional - for backward compatibility
        event_bus: EventBus = None,
        factory_name: str = "Unknown",
        factory_ref=None,  # Phase 11: Reference to factory for demand-driven production
    ):
        super().__init__(name=name)
        self.out_queue = out_queue
        self.num_items = num_items  # Legacy - may be None
        self.event_bus = event_bus
        self.factory_name = factory_name
        self.factory = factory_ref  # Reference to factory
        self.current_activity = f"{Color.BLUE}Idle{Color.RESET}"
        # IMPORTANT: make this daemon so it doesn't block exit
        self.daemon = True

        # Phase 11: Demand-driven mode
        self.demand_driven = factory_ref is not None
        self._running = True

    def _produce_item(self) -> Item:
        self.current_activity = f"{Color.GREEN}Crushing...{Color.RESET}"
        time.sleep(random.uniform(0.05, 0.2))
        return Item()

    def _should_produce(self) -> bool:
        """Check if production should continue (demand-driven)."""
        if not self.demand_driven or not self.factory:
            return False  # Legacy mode requires num_items

        # Produce if there's backlog OR items in production
        return self.factory.has_backlog() or self.factory.has_items_in_production()

    def run(self):
        if self.demand_driven:
            # Phase 11: Demand-driven production
            while self._running and self._should_produce():
                item = self._produce_item()
                self.current_activity = f"{Color.RED}Pushing...{Color.RESET}"

                if not self.out_queue.push(item):
                    self.current_activity = f"{Color.YELLOW}Shutdown{Color.RESET}"
                    break

                if self.event_bus:
                    self.event_bus.publish(
                        "item_created",
                        {
                            "station": self.name,
                            "item_id": item.id,
                            "golden": item.is_golden,
                        },
                    )

                # Idle briefly if no backlog to avoid CPU spin
                if not self._should_produce():
                    self.current_activity = f"{Color.BLUE}Idle (no demand){Color.RESET}"
                    time.sleep(0.5)  # Wait before rechecking

            self.current_activity = f"{Color.BLUE}Idle (waiting for demand){Color.RESET}"
            # Don't shutdown queue - keep running for new orders
        else:
            # Legacy: Fixed production mode
            for _ in range(self.num_items or 0):
                item = self._produce_item()
                self.current_activity = f"{Color.RED}Blocked?{Color.RESET}"

                if not self.out_queue.push(item):
                    self.current_activity = f"{Color.YELLOW}Shutdown{Color.RESET}"
                    break

                if self.event_bus:
                    self.event_bus.publish(
                        "item_created",
                        {
                            "station": self.name,
                            "item_id": item.id,
                            "golden": item.is_golden,
                        },
                    )

            self.current_activity = f"{Color.GREEN}Finished{Color.RESET}"
            self.out_queue.shutdown()
            if self.event_bus:
                self.event_bus.publish(
                    "station_shutdown",
                    {"station": self.name, "factory": self.factory_name},
                )

    def stop(self):
        """Gracefully stop production."""
        self._running = False


# ============================================================
# MOLDING STATION
# ============================================================
class MoldingStation(ScalableStation):
    def process_item(self, item: Item) -> Optional[Item]:
        self.current_activity = f"{Color.GREEN}Molding...{Color.RESET}"
        time.sleep(random.uniform(0.1, 0.3))
        return item

# ============================================================
# FILLING STATION  (Strategy + Shared Grinder)
# ============================================================
class FillingStation(ScalableStation):
    # grinder_lock = threading.Lock()  # REMOVED: Global lock caused bottleneck

    def __init__(
        self,
        name: str,
        in_queue: BoundedQueue[Item],
        out_queue: BoundedQueue[Item],
        event_bus: EventBus,
        factory_name: str = "Unknown",
        filling_strategy=None,
        factory_ref=None,  # Phase 11: Factory reference for bar_type selection
        max_workers: int = 4,  # Phase 11: Worker limit
    ):
        super().__init__(
            name, in_queue, out_queue, event_bus, factory_name, max_workers=max_workers
        )
        self.factory = factory_ref
        self.grinder_lock = threading.Lock()  # Instance-level lock (per station)

        # Phase 11: FillingStrategy integration
        if filling_strategy is None:
            # Default to WeightedFillingStrategy
            from strategies.filling_strategy import WeightedFillingStrategy
            filling_strategy = WeightedFillingStrategy()
        elif callable(filling_strategy) and not hasattr(
            filling_strategy, "choose_bar_type"
        ):
            # Legacy lambda - leave as callable
            filling_strategy = filling_strategy

        self.filling_strategy = filling_strategy

    def process_item(self, item: Item) -> Optional[Item]:
        # Phase 11: Assign bar_type using FillingStrategy
        if self.filling_strategy and self.factory:
            item.bar_type = self.filling_strategy.choose_bar_type(self.factory, item)
            filling_type = (
                item.bar_type.value.lower() if item.bar_type else "chocolate"
            )
        elif hasattr(self, "filling_strategy_legacy"):
            # Legacy lambda support
            filling_type = self.filling_strategy_legacy()
        else:
            filling_type = "chocolate"

        self.current_activity = (
            f"{Color.GREEN}Filling ({filling_type})...{Color.RESET}"
        )

        # Hazelnut requires the grinder (mutual exclusion)
        if filling_type == "hazelnut":
            with self.grinder_lock:
                time.sleep(random.uniform(0.20, 0.40))
        else:
            time.sleep(random.uniform(0.10, 0.25))

        # Update item state
        item.temperature = getattr(item, "temperature", 20) + random.uniform(1.0, 3.0)
        item.filling = filling_type

        # Publish event
        self.event_bus.publish(
            "filling_done",
            {
                "station": self.name,
                "factory": self.factory_name,
                "item_id": item.id,
                "bar_type": item.bar_type.value if item.bar_type else None,
                "filling": filling_type,
                "temperature": item.temperature,
            },
        )

        return item


# ============================================================
# QC STATION (Quality Control with Strategy Pattern)
# ============================================================
class QCStation(ScalableStation):
    """
    Quality Control station - inspects items before boxing.
    """

    def __init__(
        self,
        name: str,
        in_queue: BoundedQueue[Item],
        out_queue: BoundedQueue[Item],  # To boxing
        rework_queue: BoundedQueue[Item],  # Back to molding
        event_bus: EventBus,
        factory_name: str = "Unknown",
        qc_strategy=None,
        max_workers: int = 3,  # Phase 11: Worker limit
    ):
        super().__init__(
            name, in_queue, out_queue, event_bus, factory_name, max_workers=max_workers
        )

        from strategies.qc_strategy import TemperatureQCStrategy
        self.qc_strategy = qc_strategy or TemperatureQCStrategy()
        self.rework_queue = rework_queue

        # QC statistics
        self.passed = 0
        self.reworked = 0
        self.discarded = 0

    def process_item(self, item: Item) -> Optional[Item]:
        """QC inspection with decision logic."""
        self.current_activity = f"{Color.GREEN}Inspecting...{Color.RESET}"
        time.sleep(random.uniform(0.05, 0.15))  # Quick inspection

        # Make QC decision
        decision = self.qc_strategy.inspect(item)

        if decision == "pass":
            self.passed += 1
            self.current_activity = f"{Color.GREEN}PASS{Color.RESET}"

            # Mark item as QC passed
            item.qc_passed = True
            item.quality_score = min(1.0, item.quality_score + 0.05)

            self.event_bus.publish(
                "qc_passed",
                {
                    "station": self.name,
                    "factory": self.factory_name,
                    "item_id": item.id,
                    "temperature": item.temperature,
                    "quality_score": item.quality_score,
                },
            )

            return item  # Send to boxing

        elif decision == "rework":
            self.reworked += 1
            self.current_activity = f"{Color.YELLOW}REWORK{Color.RESET}"

            # Mark defect and reduce quality
            item.defective = True
            item.defect_reason = (
                f"Temperature out of range: {item.temperature:.1f}°C"
            )
            item.rework_count += 1
            item.quality_score = max(0.0, item.quality_score - 0.2)

            # Send back to molding (rework queue)
            if self.rework_queue:
                self.rework_queue.push(item)

            self.event_bus.publish(
                "qc_rework",
                {
                    "station": self.name,
                    "factory": self.factory_name,
                    "item_id": item.id,
                    "temperature": item.temperature,
                    "rework_count": item.rework_count,
                },
            )

            return None  # Don't send to boxing

        else:  # discard
            self.discarded += 1
            self.current_activity = f"{Color.RED}DISCARD{Color.RESET}"

            # Mark as defective
            item.defective = True
            item.defect_reason = (
                f"Temperature critical: {item.temperature:.1f}°C or random failure"
            )
            item.quality_score = 0.0

            self.event_bus.publish(
                "qc_discard",
                {
                    "station": self.name,
                    "factory": self.factory_name,
                    "item_id": item.id,
                    "temperature": item.temperature,
                    "reason": item.defect_reason,
                },
            )

            return None  # Discard


# ============================================================
# BOXING STATION (Final stage)
# ============================================================
class BoxingStation(ScalableStation):
    def __init__(
        self,
        name: str,
        in_queue: BoundedQueue[Item],
        event_bus: EventBus,
        factory_name: str = "Unknown",
        max_workers: int = 4,
    ):
        super().__init__(
            name, in_queue, None, event_bus, factory_name, max_workers=max_workers
        )
        self.items_boxed = 0
        self.total_latency = 0.0

    def process_item(self, item: Item) -> Optional[Item]:
        self.current_activity = f"{Color.GREEN}Boxing...{Color.RESET}"
        time.sleep(random.uniform(0.4, 0.6))  # bottleneck

        self.items_boxed += 1
        latency = time.time() - item.created_at
        self.total_latency += latency

        # Financial tracking
        item_cost = 5.0
        item_cost += item.rework_count * 2.0
        if item.filling in ["hazelnut", "chocolate"]:
            item_cost += 3.0

        item_revenue = 15.0 * item.quality_score
        if item.is_golden:
            item_revenue *= 2.0

        # Update item
        item.cost = item_cost
        item.value_added = item_revenue

        self.event_bus.publish(
            "item_boxed",
            {
                "station": self.name,
                "factory": self.factory_name,
                "item_id": item.id,
                "latency_total": latency,
                "golden": item.is_golden,
                "cost": item_cost,
                "revenue": item_revenue,
            },
        )

        return None
