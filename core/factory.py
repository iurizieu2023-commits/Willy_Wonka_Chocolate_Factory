# core/factory.py
import random
from typing import List, Optional

from observers.event_bus import EventBus
from core.queue import BoundedQueue
from core.station import (
    CrushingStation,
    MoldingStation,
    FillingStation,
    BoxingStation,
    QCStation,  # Added QC station
)
from utils.colors import Color


class Factory:
    """Builds + runs one full chocolate pipeline:
       Crushing → Molding → Filling → Boxing
    """

    def __init__(
        self,
        name: str,
        event_bus: EventBus,
        items_to_produce: int = 30,
        queue_capacity: int = 10,
        enable_filling: bool = True,
        lat: float = 0.0,  # Latitude
        lon: float = 0.0,  # Longitude
    ):
        self.name = name
        self.event_bus = event_bus
        self.items_to_produce = items_to_produce
        self.queue_capacity = queue_capacity
        self.enable_filling = enable_filling
        self.lat = lat  # Geographic location
        self.lon = lon
        self._db_manager = None

        # Phase 4: Metrics tracking
        import time
        self._start_time = time.time()

        # Phase 6: Legacy demand model (DEPRECATED in Phase 11)
        # This value is no longer used for production but kept for dashboard compatibility
        self.demand_score = 0.0
        self._last_demand_update = time.time()
        self._demand_update_interval = 3.0  # Update every 3 seconds

        # Phase 11: Demand-driven production tracking
        from core.chocolate_type import ChocolateType
        # Production mix targets (normalized probabilities, sum=1.0)
        self.target_mix = {
            ChocolateType.CARAMEL: 0.25,
            ChocolateType.HAZELNUT: 0.25,
            ChocolateType.DARK: 0.25,
            ChocolateType.MILK: 0.25,
        }
        # Backlog: unfulfilled orders assigned to this factory
        initial_seed = 10 if items_to_produce else 0
        self.backlog_by_type = {
            ChocolateType.CARAMEL: initial_seed,
            ChocolateType.HAZELNUT: initial_seed,
            ChocolateType.DARK: initial_seed,
            ChocolateType.MILK: initial_seed,
        }
        # Throughput: items boxed per bar type
        self.throughput_by_type = {
            ChocolateType.CARAMEL: 0,
            ChocolateType.HAZELNUT: 0,
            ChocolateType.DARK: 0,
            ChocolateType.MILK: 0,
        }

        # Financial tracking
        self.total_cost = 0.0  # Production cost
        self.total_revenue = 0.0  # Revenue from sales

        # Phase 12: Robbery security tracking
        self.last_robbery_time = 0  # Timestamp of last robbery
        self.total_robberies = 0    # Count of robberies
        self.security_level = 1.0   # Security level (0.0-1.0, higher = more secure)

        # Phase 13: VIP event shield
        self.vip_shield_until = 0   # Timestamp when VIP shield expires
        self.vip_visit_count = 0    # Total VIP visits received

        # Phase 13: Cocoa shortage tracking
        self.cocoa_shortage_multiplier = 1.0  # Cost multiplier during shortage
        self.cocoa_shortage_until = 0         # Timestamp when shortage ends

        # Phase 13: Financial tracking by category
        self.revenue_per_item = 20.0  # $15 per item
        self.cost_per_item = 10.0     # $10 base cost per item
        self.total_revenue = 0.0
        self.total_cost = 0.0
        self.breakdown_costs = 0.0    # Costs from machine breakdowns
        self.transport_losses = 0.0   # Losses from transport accidents
        # Robbery losses tracked via total_revenue adjustment

        # ----------------------------------------------------
        # Database: register queues + stations (optional)
        # ----------------------------------------------------
        self._queue_db_ids = {}
        self._station_db_ids = {}
        try:
            from database.insertions import (
                register_factory_queues,
                register_factory_stations,
            )

            # Logical queues: name → capacity
            queue_defs = {
                "Crushed": queue_capacity,
                "Molded": queue_capacity,
            }
            if enable_filling:
                queue_defs["Filled"] = queue_capacity

            self._queue_db_ids = register_factory_queues(self.name, queue_defs)

            # Station metadata: station_name → type_name
            station_kinds = {
                f"{name}-Crushing": "Crushing",
                f"{name}-Molding": "Molding",
                f"{name}-Boxing": "Boxing",
            }
            if enable_filling:
                station_kinds[f"{name}-Filling"] = "Filling"
                station_kinds[f"{name}-QC"] = "QC"

            self._station_db_ids = register_factory_stations(self.name, station_kinds)
        except Exception as e:
            print(
                f"{Color.YELLOW}[DB] Factory {self.name}: "
                f"failed to register queues/stations: {e}{Color.RESET}"
            )
            self._queue_db_ids = {}
            self._station_db_ids = {}

        # ------------------------
        # Queues between stages
        # ------------------------
        self.q_crushed = BoundedQueue(
            queue_capacity,
            db_queue_id=self._queue_db_ids.get("Crushed"),
            name=f"{name}-CrushedQ",
        )
        self.q_molded = BoundedQueue(
            queue_capacity,
            db_queue_id=self._queue_db_ids.get("Molded"),
            name=f"{name}-MoldedQ",
        )

        if enable_filling:
            self.q_filled = BoundedQueue(
                queue_capacity,
                db_queue_id=self._queue_db_ids.get("Filled"),
                name=f"{name}-FilledQ",
            )
            self.q_qc = BoundedQueue(queue_capacity, name=f"{name}-QCQ")  # After filling, before boxing

        # ------------------------
        # Stations
        # ------------------------
        self.crusher = CrushingStation(
            name=f"{name}-Crushing",
            out_queue=self.q_crushed,
            num_items=items_to_produce,
            event_bus=event_bus,
            factory_name=name,
            factory_ref=self,  # Phase 11: Pass factory reference for demand-driven production
        )

        self.molder = MoldingStation(
            name=f"{name}-Molding",
            in_queue=self.q_crushed,
            out_queue=self.q_molded,
            event_bus=event_bus,
            factory_name=name,
            max_workers=5,  # Phase 11: Bottleneck station
        )

        if enable_filling:
            # Phase 11: Use WeightedFillingStrategy for bar_type selection
            from strategies.filling_strategy import WeightedFillingStrategy

            self.filler = FillingStation(
                name=f"{name}-Filling",
                in_queue=self.q_molded,
                out_queue=self.q_filled,
                event_bus=event_bus,
                factory_name=name,
                filling_strategy=WeightedFillingStrategy(),  # Phase 11: Use strategy
                factory_ref=self,  # Phase 11: Pass factory reference for bar_type selection
                max_workers=4,  # Phase 11: Medium capacity
            )

            # QC Station (between Filling and Boxing)
            self.qc = QCStation(
                name=f"{name}-QC",
                in_queue=self.q_filled,
                out_queue=self.q_qc,
                rework_queue=self.q_crushed,  # Send rework back to crushing queue (before molding)
                event_bus=event_bus,
                factory_name=name,
                max_workers=3,  # Phase 11: Low capacity
            )

            self.boxer = BoxingStation(
                name=f"{name}-Boxing",
                in_queue=self.q_qc,  # Get items from QC
                event_bus=event_bus,
                factory_name=name,
                max_workers=4,  # Phase 11: Medium capacity
            )

            self.stations = [
                self.crusher,
                self.molder,
                self.filler,
                self.qc,  # QC station
                self.boxer,
            ]
        else:
            # No filling → molding outputs straight into boxing
            self.boxer = BoxingStation(
                name=f"{name}-Boxing",
                in_queue=self.q_molded,
                event_bus=event_bus,
                factory_name=name,
            )
            self.stations = [
                self.crusher,
                self.molder,
                self.boxer,
            ]

        # Attach DB station IDs so metrics can log snapshots
        for station in self.stations:
            db_id = self._station_db_ids.get(station.name) if hasattr(self, "_station_db_ids") else None
            setattr(station, "db_station_id", db_id)

        # Subscribe to item_boxed events for financial tracking
        self.event_bus.subscribe("item_boxed", self._on_item_boxed)

        # Subscribe to global events for real consequences
        self.event_bus.subscribe("global_event", self._on_global_event)

    def _on_item_boxed(self, event_type: str, data: dict) -> None:
        """Update financials and throughput when an item is boxed."""
        if data.get("factory") == self.name:
            # Phase 11: Track throughput by bar type
            bar_type_str = data.get("bar_type")
            if bar_type_str:
                from core.chocolate_type import ChocolateType
                try:
                    bar_type = ChocolateType(bar_type_str)
                    self.throughput_by_type[bar_type] = self.throughput_by_type.get(bar_type, 0) + 1
                except (ValueError, KeyError):
                    pass  # Unknown bar type, skip

            # Financial tracking with cocoa shortage multiplier (Phase 13)
            import time
            current_cost = self.cost_per_item

            # Apply cocoa shortage multiplier if active
            if time.time() < self.cocoa_shortage_until:
                current_cost *= self.cocoa_shortage_multiplier

            self.total_cost += current_cost
            self.total_revenue += self.revenue_per_item

            # Phase 13: Log per-transaction to profit_ledger (optional DB manager)
            if hasattr(self, "_db_manager") and self._db_manager:
                self._db_manager.log_production_transaction(
                    factory=self,
                    quantity=1,
                    cost_per_item=current_cost,
                    revenue_per_item=self.revenue_per_item,
                )

    def _on_global_event(self, event_type: str, data: dict) -> None:
        """Handle global events that affect this factory."""
        if data.get("type") == "transport_accident":
            # This factory only updates financials (DemandEngine already reduced quantity)
            loss_pct = data.get("loss_percent", 0)
            city = data.get("city", "?")
            print(f"{Color.RED}🚚 Transport accident affecting shipments to {city}!{Color.RESET}")
            return


        if data.get("factory") != self.name:
            return  # Not for this factory

        event_subtype = data.get("type")

        if event_subtype == "robbery":
            # Actually reduce boxed items
            stolen = data.get("stolen", 0)
            before = self.boxer.items_boxed
            self.boxer.items_boxed = max(0, self.boxer.items_boxed - stolen)
            actual_stolen = before - self.boxer.items_boxed

            # Reduce revenue (items were stolen after boxing)
            loss = actual_stolen * 15.0  # Average revenue per item
            self.total_revenue = max(0, self.total_revenue - loss)

            print(
                f"{Color.RED}🦹 ROBBERY at {self.name}: "
                f"Lost {actual_stolen} boxed items (${loss:.0f} revenue){Color.RESET}"
            )

        elif event_subtype == "vip_visit":
            # Boost demand score
            boost = data.get("boost", 1.2)
            old_demand = self.demand_score
            self.demand_score *= boost
            self.demand_score = min(2.0, self.demand_score)  # Cap at 2.0

            print(
                f"{Color.GREEN}🌟 VIP VISIT at {self.name}: "
                f"Demand boosted {old_demand:.2f} → {self.demand_score:.2f}{Color.RESET}"
            )

        elif event_subtype == "machine_breakdown":
            # Slow down specific station
            station_name = data.get("station")
            duration = data.get("duration", 5)

            target_station = None
            if "Crushing" in station_name:
                target_station = self.crusher
            elif "Molding" in station_name:
                target_station = self.molder
            elif "Filling" in station_name:
                target_station = getattr(self, "filler", None)
            elif "QC" in station_name:
                target_station = getattr(self, "qc", None)

            if target_station and hasattr(target_station, "trigger_breakdown"):
                target_station.trigger_breakdown(duration)

                breakdown_cost = duration * 5.0
                print(f"[DEBUG] {self.name} breakdown_costs={self.breakdown_costs}, total_cost={self.total_cost}")

                self.breakdown_costs += breakdown_cost
                self.total_cost += breakdown_cost

                # ✅ Log to DB correctly
                if self._db_manager:
                    try:
                        self._db_manager.log_breakdown_cost(self, breakdown_cost)
                    except Exception:
                        pass

                print(
                    f"{Color.RED}🔧 BREAKDOWN at {self.name} {station_name}: "
                    f"Halted for {duration}s (Cost: ${breakdown_cost:.2f}){Color.RESET}"
                )




    # ----------------------------------------------------
    # Phase 11: Demand-driven production methods
    # ----------------------------------------------------
    def has_backlog(self) -> bool:
        """Returns True if any bar type has unfulfilled orders."""
        return sum(self.backlog_by_type.values()) > 0

    def has_items_in_production(self) -> bool:
        """Returns True if any items are in queues."""
        return (
            self.q_crushed.size() > 0
            or self.q_molded.size() > 0
            or (self.enable_filling and self.q_filled.size() > 0)
        )

    def total_backlog(self) -> int:
        """Total unfulfilled orders across all bar types."""
        return sum(self.backlog_by_type.values())

    def update_target_mix(self, new_mix: dict) -> None:
        """Update production mix targets (used by Supervisor).

        Args:
            new_mix: Dict[ChocolateType, float] with normalized proportions
        """
        # Normalize to ensure sum = 1.0
        total = sum(new_mix.values())
        if total > 0:
            self.target_mix = {k: v / total for k, v in new_mix.items()}

    # ----------------------------------------------------
    def start(self):
        """Start all stations (handles both regular and scalable stations)."""
        for s in self.stations:
            # Phase 2: ScalableStations need start_workers(), regular threads need start()
            if hasattr(s, "start_workers"):
                s.start_workers(1)  # Start with 1 worker by default
            else:
                s.start()

    # ----------------------------------------------------
    def wait_until_done(self):
        """Wait for all stations to complete (in parallel)."""
        import threading

        # Wait for all stations in parallel
        wait_threads = []
        for s in self.stations:
            if hasattr(s, "wait_until_done"):
                t = threading.Thread(target=s.wait_until_done, daemon=True)
            else:
                t = threading.Thread(target=s.join, daemon=True)
            t.start()
            wait_threads.append(t)

        # Join all wait threads
        for t in wait_threads:
            t.join()

        # stop dashboard AFTER all stations finish
        if hasattr(self, "dashboard"):
            self.dashboard.stop()
            self.dashboard.join()  # optional but cleaner

        print(f"{Color.BOLD}=== Factory {self.name} finished ==={Color.RESET}")

        # Final metrics
        print(f"  Items boxed: {self.boxer.items_boxed}")
        avg = (
            self.boxer.total_latency / self.boxer.items_boxed
            if self.boxer.items_boxed > 0
            else 0
        )
        print(f"  Avg latency: {avg:.3f} s")

    def get_queues(self):
        queues = {
            "Crushed": self.q_crushed,
            "Molded": self.q_molded,
        }
        if self.enable_filling:
            queues["Filled"] = self.q_filled
        return queues

    # ============================================================
    # Phase 4: Metrics API + DB snapshots
    # ============================================================
    def get_factory_metrics(self):
        """Return factory-level metrics snapshot."""
        from core.metrics import FactoryMetrics
        import time

        # Lazy DB import so DB failures never crash the sim
        try:
            from database.insertions import insert_factory_snapshot
        except Exception:
            insert_factory_snapshot = None  # type: ignore

        total_boxed = self.boxer.items_boxed
        wip = sum(
            q.size()
            for q in [self.q_crushed, self.q_molded]
            + ([self.q_filled] if self.enable_filling else [])
        )

        # Defect tracking from QC station
        if hasattr(self, "qc"):
            defect_count = self.qc.reworked + self.qc.discarded
            total_inspected = (
                self.qc.passed + self.qc.reworked + self.qc.discarded
            )
            defect_rate = (
                defect_count / total_inspected if total_inspected > 0 else 0.0
            )
        else:
            defect_count = 0
            defect_rate = 0.0

        # Throughput calculation (items per minute)
        uptime = time.time() - getattr(self, "_start_time", time.time())
        throughput_1m = (total_boxed / uptime * 60) if uptime > 0 else 0

        # Demand score
        demand_score = getattr(self, "demand_score", 1.0)

        # Financial metrics
        total_cost = getattr(self, "total_cost", 0.0)
        total_revenue = getattr(self, "total_revenue", 0.0)
        total_revenue = getattr(self, "total_revenue", 0.0)
        transport_losses = getattr(self, "transport_losses", 0.0)
        profit = total_revenue - total_cost - transport_losses

        metrics = FactoryMetrics(
            factory_name=self.name,
            total_boxed=total_boxed,
            wip=wip,
            defect_count=defect_count,
            defect_rate=defect_rate,
            throughput_1m=throughput_1m,
            uptime=uptime,
            demand_score=demand_score,
            total_cost=total_cost,
            total_revenue=total_revenue,
            profit=profit,
        )

        # NEW: write factory snapshot to DB
        if insert_factory_snapshot:
            try:
                insert_factory_snapshot(
                    factory_name=self.name,
                    throughput_1m=int(throughput_1m),
                    wip=int(wip),
                    defect_rate=float(defect_rate),
                    cash=float(profit),
                )
            except Exception:
                pass

        return metrics

    def get_wip_golden_tickets(self) -> int:
        """Count golden tickets currently in production (WIP)."""
        count = 0
        queues = [self.q_crushed, self.q_molded]
        if self.enable_filling:
            queues.extend(
                [
                    self.q_filled,
                    getattr(self, "q_qc", None),
                    getattr(self, "q_rework", None),
                ]
            )

        for q in queues:
            if q:
                items = q.peek_items()
                count += sum(1 for item in items if item.is_golden)
        return count

    def get_station_metrics(self):
        """Return list of station-level metrics."""
        from core.metrics import StationMetrics

        # Lazy DB import
        try:
            from database.insertions import insert_station_snapshot
        except Exception:
            insert_station_snapshot = None  # type: ignore

        metrics: List[StationMetrics] = []
        for station in self.stations:
            # Skip non-scalable stations or get basic info
            if not hasattr(station, "stress_score"):
                continue

            utilization = station.get_utilization()
            station_metrics = StationMetrics(
                station_name=station.name,
                factory_name=self.name,
                current_activity=station.current_activity,
                utilization=utilization,
                is_faulted=station.is_faulted,
                stress_score=station.stress_score,
                avg_latency_ms=0.0,
                workers=len(station.workers),
                in_queue_size=station.in_queue.size(),
                out_queue_size=station.out_queue.size()
                if station.out_queue
                else 0,
                last_processed_item_id=None,
                items_processed=station._items_processed,
            )
            metrics.append(station_metrics)

            # NEW: log station snapshot to DB
            if insert_station_snapshot:
                db_id = getattr(station, "db_station_id", None)
                if db_id is not None:
                    try:
                        insert_station_snapshot(
                            station_id=db_id,
                            workers=len(station.workers),
                            utilization=utilization,
                            faulted=bool(station.is_faulted),
                            avg_latency_ms=None,
                        )
                    except Exception:
                        pass

        return metrics

    def get_queue_metrics(self):
        """Return list of queue-level metrics."""
        from core.metrics import QueueMetrics

        metrics: List[QueueMetrics] = []
        queues = [
            ("Crushed", self.q_crushed),
            ("Molded", self.q_molded),
        ]
        if self.enable_filling:
            queues.append(("Filled", self.q_filled))

        for name, queue in queues:
            size = queue.size()
            max_size = queue.capacity
            utilization = size / max_size if max_size > 0 else 0.0

            queue_metrics = QueueMetrics(
                name=f"{self.name}-{name}",
                size=size,
                max_size=max_size,
                utilization=utilization,
                blocked=utilization >= 1.0,
            )
            metrics.append(queue_metrics)

        return metrics

    def update_demand(self) -> None:
        """
        Phase 6: Update demand score using demand model.
        Should be called periodically (e.g., from supervisor or main loop).
        """
        import time
        current_time = time.time()

        # Only update if interval has passed
        if current_time - self._last_demand_update < self._demand_update_interval:
            return

        # Update demand using model
        new_demand = self.demand_model.update_demand(self)
        self.demand_score = new_demand
        self._last_demand_update = current_time

        # Publish demand change event
        self.event_bus.publish(
            "demand_updated",
            {
                "factory": self.name,
                "demand_score": self.demand_score,
                "model": self.demand_model.get_model_name(),
            },
        )
