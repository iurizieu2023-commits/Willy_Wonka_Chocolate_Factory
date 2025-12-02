# database/db_manager.py

"""
Database Manager for Willy Wonka Simulation.

Centralizes database operations and provides high-level interface
for logging simulation metrics, events, and transactions.
"""

import json
import time
from typing import Optional, Dict, List
from .db import initialize_database, get_connection
from .insertions import (
    register_factory_queues,
    register_factory_stations,
    insert_factory_snapshot,
    insert_station_snapshot,
    _get_or_create_factory_id,
)
from .db_insertions_extended import (
    insert_global_event,
    insert_profit_entry,
    insert_city,
    insert_shipment,
    update_shipment_arrival,
)


class DatabaseManager:
    """
    Centralized database manager for simulation logging.
    
    Handles:
    - Initialization and registration
    - Periodic snapshots
    - Event logging
    - Financial transactions
    - Shipment tracking
    """
    
    def __init__(self, enable_logging: bool = True):
        """
        Initialize database manager.
        
        Args:
            enable_logging: If False, all logging is skipped (no-op mode)
        """
        self.enabled = enable_logging
        
        # ID mappings
        self.factory_ids: Dict[str, int] = {}
        self.station_ids: Dict[str, int] = {}
        self.queue_ids: Dict[str, int] = {}
        self.city_ids: Dict[str, int] = {}
        self.shipment_ids: Dict[str, int] = {}  # order_id -> shipment_id

        # NEW: expose a sqlite connection so report.py can use it
        self.conn = None
        
        if self.enabled:
            initialize_database()
            # keep a persistent connection for reporting / summaries
            try:
                self.conn = get_connection()
            except Exception:
                self.conn = None
            print("✅ Database initialized")

    
    def register_factory(self, factory) -> int:
        """
        Register a factory and its stations/queues in the database.
        
        Returns:
            factory_id: Database ID for the factory
        """
        if not self.enabled:
            return 0
        
        from .insertions import _get_or_create_factory_id
        
        # Get factory ID
        factory_id = _get_or_create_factory_id(factory.name)
        self.factory_ids[factory.name] = factory_id
        
        # Register stations
        station_kinds = {}
        for station in factory.stations:
            # Map station instance name to type
            station_type = station.name.split("-")[-1]  # e.g., "WonkaFactory-Crushing" -> "Crushing"
            station_kinds[station.name] = station_type
        
        station_ids = register_factory_stations(factory.name, station_kinds)
        self.station_ids.update(station_ids)
        
        # Register queues
        queue_defs = {
            "Crushed": factory.q_crushed.capacity,
            "Molded": factory.q_molded.capacity,
        }
        
        if hasattr(factory, 'q_filled'):
            queue_defs["Filled"] = factory.q_filled.capacity
        
        if hasattr(factory, 'q_qc'):
            queue_defs["QC"] = factory.q_qc.capacity
        
        queue_ids = register_factory_queues(factory.name, queue_defs)
        # Store with factory prefix for uniqueness
        for q_name, q_id in queue_ids.items():
            self.queue_ids[f"{factory.name}-{q_name}"] = q_id
        
        print(f"✅ Registered factory: {factory.name} (ID: {factory_id})")
        return factory_id
    
    def register_city(self, city, region: str = None) -> int:
        """Register a city in the database."""
        if not self.enabled:
            return 0
        
        city_id = insert_city(city.name, region=region, margin_per_unit=5.0)
        self.city_ids[city.name] = city_id
        return city_id
    
    def log_factory_snapshot(self, factory) -> None:
        """Log factory metrics snapshot."""
        if not self.enabled:
            return
        
        metrics = factory.get_factory_metrics()
        profit = factory.total_revenue - factory.total_cost
        
        insert_factory_snapshot(
            factory_name=factory.name,
            throughput_1m=int(metrics.throughput_1m),
            wip=int(metrics.wip),
            defect_rate=float(metrics.defect_rate),
            cash=float(profit)
        )
    
    def log_station_snapshot(self, factory, station) -> None:
        """Log station metrics snapshot."""
        if not self.enabled:
            return
        
        station_id = self.station_ids.get(station.name)
        if not station_id:
            return  # Station not registered
        
        utilization = station.utilization() if hasattr(station, 'utilization') else 0.0
        faulted = getattr(station, 'is_faulted', False)
        workers = getattr(station, 'num_workers', 0)
        
        insert_station_snapshot(
            station_id=station_id,
            workers=workers,
            utilization=utilization,
            faulted=faulted,
            avg_latency_ms=None  # Can calculate later if needed
        )
    
    def log_event(self, event_data: dict) -> Optional[int]:
        """
        Log a global event to the database.
        
        Args:
            event_data: Event dict from EventEngine
        
        Returns:
            event_id or None
        """
        if not self.enabled:
            return None
        
        event_type = event_data.get("type", "unknown")
        factory_name = event_data.get("factory")
        city_name = event_data.get("city")
        
        # Determine scope
        if factory_name and city_name:
            scope = "factory_city"
        elif factory_name:
            scope = "factory"
        elif city_name:
            scope = "city"
        else:
            scope = "global"
        
        # Get IDs
        factory_id = self.factory_ids.get(factory_name) if factory_name else None
        city_id = self.city_ids.get(city_name) if city_name else None
        
        # Extract effect data
        effect = {
            k: v for k, v in event_data.items()
            if k not in ["type", "factory", "city", "msg"]
        }
        
        # TTL for timed events
        ttl_s = event_data.get("duration", event_data.get("shield_duration"))
        
        event_id = insert_global_event(
            event_type=event_type,
            scope=scope,
            factory_id=factory_id,
            city_id=city_id,
            station_id=None,
            effect=json.dumps(effect),
            ttl_s=ttl_s
        )
        
        return event_id
    
    def log_production_transaction(self, factory, quantity: int, cost_per_item: float, revenue_per_item: float) -> None:
        """
        Log a production transaction (when items are boxed).
        
        Args:
            factory: Factory instance
            quantity: Number of items boxed
            cost_per_item: Cost per item (may include cocoa multiplier)
            revenue_per_item: Revenue per item
        """
        if not self.enabled:
            return
        
        factory_id = self.factory_ids.get(factory.name)
        if not factory_id:
            return
        
        insert_profit_entry(
            factory_id=factory_id,
            revenue=revenue_per_item * quantity,
            cogs=cost_per_item * quantity,
            event_cost=0.0,
            logistics_cost=0.0,
            ref_type="production",
            ref_id=None
        )
    
    def log_breakdown_cost(self, factory, cost: float) -> None:
        """Log breakdown repair cost."""
        if not self.enabled:
            return
        
        factory_id = self.factory_ids.get(factory.name)
        if not factory_id:
            return
        
        insert_profit_entry(
            factory_id=factory_id,
            revenue=0.0,
            cogs=0.0,
            event_cost=cost,
            logistics_cost=0.0,
            ref_type="breakdown",
            ref_id=None
        )
    
    def log_transport_loss(self, shipment_id: int, lost_units: int, loss_value: float) -> None:
        """Log transport spoilage + its financial impact."""
        if not self.enabled:
            return

        from .db_insertions_extended import insert_transport_loss

        insert_transport_loss(
            shipment_id=shipment_id,
            lost_units=lost_units,
            loss_value=loss_value,
        )


    def log_shipment_start(self, order) -> Optional[int]:
        """
        Log when a shipment departs.
        
        Returns:
            shipment_id or None
        """
        if not self.enabled:
            return None
        
        factory_id = self.factory_ids.get(order.assigned_factory)
        city_id = self.city_ids.get(order.city_name)
        
        if not factory_id or not city_id:
            return None
        
        import uuid
        truck_id = f"TRUCK-{str(uuid.uuid4())[:8]}"
        
        shipment_id = insert_shipment(
            factory_id=factory_id,
            city_id=city_id,
            qty=order.quantity,
            status=order.status,
            truck_id=truck_id
        )
        
        # Store mapping
        order_key = f"{order.city_name}-{order.bar_type.value}-{order.created_at}"
        self.shipment_ids[order_key] = shipment_id
        
        return shipment_id
    
    def log_shipment_arrival(self, order, transit_time_s: int) -> None:
        """Log when a shipment arrives."""
        if not self.enabled:
            return
        
        order_key = f"{order.city_name}-{order.bar_type.value}-{order.created_at}"
        shipment_id = self.shipment_ids.get(order_key)
        
        if shipment_id:
            update_shipment_arrival(
                shipment_id=shipment_id,
                status="DELIVERED",
                transit_time_s=transit_time_s,
                spoilage=0
            )
    
    def log_supervisor_action(
        self,
        factory,
        station=None,
        action_type: str = "worker_change",
        delta_workers: int = 0,
        reason: str = None
    ) -> None:
        """
        Log a supervisor action/decision.
        
        Args:
            factory: Factory instance
            station: Station instance (if applicable)
            action_type: Type of action
            delta_workers: Change in workers (+1, -1)
            reason: Reasoning for action
        """
        if not self.enabled:
            return
        
        factory_id = self.factory_ids.get(factory.name)
        if not factory_id:
            return
        
        station_id = None
        if station:
            station_id = self.station_ids.get(station.name)
        
        from .db_insertions_extended import insert_supervisor_action
        insert_supervisor_action(
            factory_id=factory_id,
            station_id=station_id,
            action_type=action_type,
            delta_workers=delta_workers,
            reason=reason,
            strategy_id=None
        )
    
    def close(self) -> None:
        """Clean shutdown (if needed)."""
        if self.enabled:
            # NEW: close the SQLite connection if we created one
            conn = getattr(self, "conn", None)
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            print("✅ Database operations complete")


# Singleton instance for easy access
_db_manager: Optional[DatabaseManager] = None


def get_db_manager(enable_logging: bool = True) -> DatabaseManager:
    """Get or create the global DatabaseManager instance."""
    global _db_manager
    if _db_manager is None:
        _db_manager = DatabaseManager(enable_logging=enable_logging)
    return _db_manager
