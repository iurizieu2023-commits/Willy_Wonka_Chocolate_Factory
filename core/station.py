# core/station.py
import threading
import time
import random
from typing import Optional

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
        self.daemon = False

    # ---- Primitive operation to override ----
    def process_item(self, item: Item) -> Optional[Item]:
        """Default implementation (safe fallback)."""
        self.current_activity = f"{Color.GREEN}{self.name}...{Color.RESET}"
        time.sleep(random.uniform(0.1, 0.3))
        return item

    # ---- Template Method (DO NOT OVERRIDE) ----
    def run(self) -> None:
        while True:
            self.current_activity = f"{Color.BLUE}Waiting...{Color.RESET}"
            item = self.in_queue.pop()

            if item is None:
                # Upstream finished
                self.current_activity = f"{Color.YELLOW}Shutdown{Color.RESET}"
                if self.out_queue:
                    self.out_queue.shutdown()
                self.event_bus.publish("station_shutdown", {
                    "station": self.name, 
                    "factory": self.factory_name
                })
                break

            # Process the item (delegated to subclass)
            try:
                start = time.time()
                processed_item = self.process_item(item)
                duration = time.time() - start
                
                # Update metrics
                self._total_processing_time += duration
                self._items_processed += 1
                self.utilization = self._total_processing_time / (time.time() - self._start_time) if (time.time() - self._start_time) > 0 else 0

                if processed_item:
                    # Push to next queue
                    if self.out_queue:
                        self.current_activity = f"{Color.RED}Blocked?{Color.RESET}" # Re-added activity update
                        ok = self.out_queue.push(processed_item)
                        if not ok:
                            self.current_activity = f"{Color.YELLOW}Shutdown{Color.RESET}"
                            break
                    
                    # Publish event
                    self.current_activity = f"{Color.GREEN}Done{Color.RESET}" # Re-added activity update
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
    - Multiple worker threads (Manager pattern)
    - Dynamic add/remove workers
    - Stress tracking and fault detection
    
    Usage:
        station = ScalableStation(...)
        station.start_workers(2)  # Start with 2 workers
        station.add_worker()      # Scale up
        station.remove_worker()   # Scale down
    """
    
    def __init__(
        self,
        name: str,
        in_queue: BoundedQueue[Item],
        out_queue: Optional[BoundedQueue[Item]],
        event_bus: EventBus,
        factory_name: str = "Unknown",
        max_workers: int = 5,  # Phase 11: Worker scaling limit
    ) -> None:
        # Don't call super().__init__() for threading.Thread
        # because we manage workers manually
        threading.Thread.__init__(self, name=name)
        
        self.in_queue = in_queue
        self.out_queue = out_queue
        self.event_bus = event_bus
        self.factory_name = factory_name
        self.max_workers = max_workers  # Phase 11: Store max_workers limit
        self.current_activity = f"{Color.BLUE}Idle{Color.RESET}"
        self.daemon = False
        
        # Phase 2: Worker management
        self.workers: List[threading.Thread] = []
        self.worker_stop_events: List[threading.Event] = []
        self._worker_id_counter = 1
        self._running = True
        self._lock = threading.Lock()
        
        # Metrics
        self.utilization = 0.0
        self.stress_score = 0.0
        self.is_faulted = False
        self.breakdown_until = 0.0
        self._stress_lock = threading.Lock()
        
        # Metrics for utilization
        self._total_processing_time = 0.0
        self._total_idle_time = 0.0
        self._items_processed = 0
        
    def start_workers(self, n: int = 1) -> None:
        """Bootstrap initial workers."""
        with self._lock:
            for _ in range(n):
                self._spawn_worker()
                
    def add_worker(self) -> bool:
        """Dynamically add a worker thread. Returns True if successful."""
        with self._lock:
            if not self._running:
                return False
            
            # Phase 11: Enforce worker limit
            # Note: self.max_workers is expected to be set by BaseStation's __init__
            # or explicitly in ScalableStation's __init__.
            # The current ScalableStation.__init__ does not call BaseStation.__init__
            # and does not set self.max_workers, which might lead to an AttributeError.
            # Assuming self.max_workers will be available.
            if len(self.workers) >= self.max_workers:
                return False  # At capacity
            
            self._spawn_worker()
            self.event_bus.publish("worker_added", {
                "station": self.name,
                "factory": self.factory_name,
                "count": len(self.workers),
                "max": self.max_workers,
            })
            return True
            
    def remove_worker(self) -> None:
        """Gracefully remove one worker thread."""
        with self._lock:
            if len(self.workers) <= 1:
                # Keep at least 1 worker
                return
            if self.workers:
                # Worker will exit when it sees _running=False for its ID
                worker = self.workers.pop()
                # Note: Can't cleanly stop a single worker without complex signaling
                # For now, we'll just reduce the count and let natural shutdown occur
                self.event_bus.publish("worker_removed", {
                    "station": self.name,
                    "factory": self.factory_name,
                    "total_workers": len(self.workers)
                })
    
    def _spawn_worker(self) -> None:
        """Internal: spawn a new worker thread."""
        worker_id = self._worker_id_counter
        self._worker_id_counter += 1
        stop_event = threading.Event()
        worker = threading.Thread(
            target=self._worker_loop,
            args=(stop_event,),
            name=f"{self.name}-Worker-{worker_id}",
            daemon=True
        )
        self.workers.append(worker)
        self.worker_stop_events.append(stop_event)
        worker.start()
        
    def _worker_loop(self, stop_event: threading.Event) -> None:
        """Worker thread loop."""
        while not stop_event.is_set():
            # Check for breakdown
            if time.time() < self.breakdown_until:
                self.current_activity = f"{Color.RED}REPAIRING...{Color.RESET}"
                time.sleep(0.5) # Wait a bit before re-checking
                continue
            elif self.is_faulted and time.time() >= self.breakdown_until:
                self.is_faulted = False  # Repair complete
                self.event_bus.publish("station_repaired", {
                    "station": self.name,
                    "factory": self.factory_name
                })
            
            # Try to get item with timeout to allow checking stop_event
            # Use a timeout to periodically check the stop_event
            item = self.in_queue.pop(timeout=0.1) 

            if item is None:
                # Queue empty or shutdown
                if self.in_queue._done: # Check if the queue is explicitly shut down
                    break # Exit worker loop if upstream is done
                self.current_activity = f"{Color.BLUE}Waiting...{Color.RESET}"
                # If item is None due to timeout, loop again to check stop_event/breakdown
                continue

            # Process the item (delegated to subclass)
            start = time.time()
            processed = self.process_item(item)
            duration = time.time() - start
            
            with self._stress_lock:
                self._items_processed += 1
                self._total_processing_time += duration

            # Send downstream if needed
            if processed is not None and self.out_queue is not None:
                self.current_activity = f"{Color.RED}Blocked?{Color.RESET}"
                ok = self.out_queue.push(processed)
                if not ok:
                    self.current_activity = f"{Color.YELLOW}Shutdown{Color.RESET}"
                    break

            # Emit processed event
            self.current_activity = f"{Color.GREEN}Done{Color.RESET}"
            self.event_bus.publish(
                "item_processed",
                {
                    "station": self.name,
                    "item_id": item.id,
                    "latency_stage": duration,
                    "golden": item.is_golden,
                },
            )
            
            # Phase 2: Update stress after each item
            self.update_stress(duration)

        self.current_activity = f"{Color.GREEN}Finished{Color.RESET}"
        
    def update_stress(self, processing_time: float) -> None:
        """Update stress score based on queue size, processing time, temperature variance."""
        with self._stress_lock:
            queue_size = self.in_queue.size()
            queue_capacity = self.in_queue.capacity
            
            # Stress factors:
            # 1. Queue utilization (0-1)
            queue_stress = queue_size / queue_capacity if queue_capacity > 0 else 0
            
            # 2. Processing latency (normalized, assume >1s is high)
            latency_stress = min(processing_time / 1.0, 1.0)
            
            # Combine (weighted average)
            new_stress = 0.6 * queue_stress + 0.4 * latency_stress
            
            # Smooth with exponential moving average
            alpha = 0.3
            self.stress_score = alpha * new_stress + (1 - alpha) * self.stress_score
            
            # Fault detection (threshold)
            FAULT_THRESHOLD = 0.8
            if self.stress_score > FAULT_THRESHOLD and not self.is_faulted:
                self.is_faulted = True
                self.event_bus.publish("station_fault", {
                    "station": self.name,
                    "factory": self.factory_name,
                    "stress_score": self.stress_score
                })
                
    def repair(self) -> None:
        """Repair the station (clear fault, reset stress)."""
        with self._stress_lock:
            self.is_faulted = False
            self.stress_score = self.stress_score * 0.5  # Reduce stress
            self.event_bus.publish("station_repaired", {
                "station": self.name,
                "factory": self.factory_name
            })
            
    def get_utilization(self) -> float:
        """Return utilization (0-1): fraction of time spent processing."""
        with self._stress_lock:
            total_time = self._total_processing_time + self._total_idle_time
            if total_time == 0:
                return 0.0
            return self._total_processing_time / total_time
            
    def wait_until_done(self) -> None:
        """Wait for all workers to finish."""
        for worker in self.workers:
            if worker.is_alive():
                worker.join()
                
    def stop(self) -> None:
        """Signal all workers to stop."""
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
        self.daemon = False
        
        # Phase 11: Demand-driven mode
        self.demand_driven = (factory_ref is not None)
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
                        {"station": self.name, "item_id": item.id, "golden": item.is_golden},
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
                        {"station": self.name, "item_id": item.id, "golden": item.is_golden},
                    )

            self.current_activity = f"{Color.GREEN}Finished{Color.RESET}"
            self.out_queue.shutdown()
            if self.event_bus:
                self.event_bus.publish("station_shutdown", {
                    "station": self.name,
                    "factory": self.factory_name
                })
    
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
    grinder_lock = threading.Lock()  # Shared lock across all filling stations

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
        super().__init__(name, in_queue, out_queue, event_bus, factory_name, max_workers=max_workers)
        self.factory = factory_ref
        
        # Phase 11: FillingStrategy integration
        if filling_strategy is None:
            # Default to WeightedFillingStrategy
            from strategies.filling_strategy import WeightedFillingStrategy
            filling_strategy = WeightedFillingStrategy()
        elif callable(filling_strategy) and not hasattr(filling_strategy, 'choose_bar_type'):
            # Legacy lambda - wrap it
            filling_strategy = filling_strategy
        
        self.filling_strategy = filling_strategy

    def process_item(self, item: Item) -> Optional[Item]:
        # Phase 11: Assign bar_type using FillingStrategy
        if self.filling_strategy and self.factory:
            item.bar_type = self.filling_strategy.choose_bar_type(self.factory, item)
            filling_type = item.bar_type.value.lower() if item.bar_type else "chocolate"
        elif hasattr(self, 'filling_strategy_legacy'):
            # Legacy lambda support
            filling_type = self.filling_strategy_legacy()
        else:
            filling_type = "chocolate"
        
        self.current_activity = (
            f"{Color.GREEN}Filling ({filling_type})...{Color.RESET}"
        )

        # Hazelnut requires the grinder (mutual exclusion)
        if filling_type == "hazelnut":
            with FillingStation.grinder_lock:
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
    
    Features:
    - Uses QCStrategy for inspection decisions
    - Pass → send to boxing
    - Rework → send back to molding
    - Discard → remove from pipeline
    - Tracks defect statistics
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
        super().__init__(name, in_queue, out_queue, event_bus, factory_name, max_workers=max_workers)
        
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
        
        if decision == 'pass':
            self.passed += 1
            self.current_activity = f"{Color.GREEN}PASS{Color.RESET}"
            
            # Mark item as QC passed
            item.qc_passed = True
            item.quality_score = min(1.0, item.quality_score + 0.05)  # Boost quality
            
            self.event_bus.publish("qc_passed", {
                "station": self.name,
                "factory": self.factory_name,
                "item_id": item.id,
                "temperature": item.temperature,
                "quality_score": item.quality_score
            })
            
            return item  # Send to boxing
            
        elif decision == 'rework':
            self.reworked += 1
            self.current_activity = f"{Color.YELLOW}REWORK{Color.RESET}"
            
            # Mark defect and reduce quality
            item.defective = True
            item.defect_reason = f"Temperature out of range: {item.temperature:.1f}°C"
            item.rework_count += 1
            item.quality_score = max(0.0, item.quality_score - 0.2)
            
            # Send back to molding (rework queue)
            if self.rework_queue:
                self.rework_queue.push(item)
            
            self.event_bus.publish("qc_rework", {
                "station": self.name,
                "factory": self.factory_name,
                "item_id": item.id,
                "temperature": item.temperature,
                "rework_count": item.rework_count
            })
            
            return None  # Don't send to boxing
            
        else:  # discard
            self.discarded += 1
            self.current_activity = f"{Color.RED}DISCARD{Color.RESET}"
            
            # Mark as defective
            item.defective = True
            item.defect_reason = f"Temperature critical: {item.temperature:.1f}°C or random failure"
            item.quality_score = 0.0
            
            self.event_bus.publish("qc_discard", {
                "station": self.name,
                "factory": self.factory_name,
                "item_id": item.id,
                "temperature": item.temperature,
                "reason": item.defect_reason
            })
            
            return None  # Discard (don't send anywhere)


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
        max_workers: int = 4,  # Phase 11: Worker limit
    ):
        super().__init__(name, in_queue, None, event_bus, factory_name, max_workers=max_workers)
        self.items_boxed = 0
        self.total_latency = 0.0

    def process_item(self, item: Item) -> Optional[Item]:
        self.current_activity = f"{Color.GREEN}Boxing...{Color.RESET}"
        time.sleep(random.uniform(0.4, 0.6))  # bottleneck

        self.items_boxed += 1
        latency = time.time() - item.created_at
        self.total_latency += latency
        
        # Financial tracking
        # Cost: $5 base + $2 per rework + $3 for premium fillings
        item_cost = 5.0
        item_cost += item.rework_count * 2.0
        if item.filling in ["hazelnut", "chocolate"]:
            item_cost += 3.0
        
        # Revenue: $15 base * quality_score multiplier * golden multiplier
        item_revenue = 15.0 * item.quality_score
        if item.is_golden:
            item_revenue *= 2.0  # Golden tickets worth 2x
        
        # Update factory financials (find parent factory via factory_name)
        # This is a bit hacky but works - we'd ideally pass factory reference
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
