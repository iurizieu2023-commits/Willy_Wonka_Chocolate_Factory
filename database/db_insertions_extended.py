# database/db_insertions_extended.py
"""
Extended database insertion functions for Phase 13.
Adds event logging, financial ledger, and logistics tracking.
"""

from datetime import datetime, timezone
import json
from .db import get_connection


def _utc_now() -> str:
    """Return current UTC time as ISO string with timezone."""
    return datetime.now(timezone.utc).isoformat()


def insert_global_event(
    event_type: str,
    scope: str,
    factory_id: int = None,
    city_id: int = None,
    station_id: int = None,
    effect: str = "{}",
    ttl_s: int = None
) -> int:
    """
    Insert a global event into the global_events table.
    
    Returns the event_id for linking event_impacts.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO global_events(
            ts, type, scope, factory_id, city_id, station_id, effect, ttl_s
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _utc_now(),
            event_type,
            scope,
            factory_id,
            city_id,
            station_id,
            effect,
            ttl_s
        ),
    )
    
    event_id = cur.lastrowid
    conn.commit()
    conn.close()
    return event_id


def insert_profit_entry(
    factory_id: int = None,
    city_id: int = None,
    revenue: float = 0.0,
    cogs: float = 0.0,
    event_cost: float = 0.0,
    logistics_cost: float = 0.0,
    ref_type: str = None,
    ref_id: int = None
) -> None:
    """
    Insert a financial transaction into the profit_ledger.
    
    profit is auto-calculated: revenue - cogs - event_cost - logistics_cost
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO profit_ledger(
            ts, factory_id, city_id, revenue, cogs, event_cost, logistics_cost, ref_type, ref_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            _utc_now(),
            factory_id,
            city_id,
            float(revenue),
            float(cogs),
            float(event_cost),
            float(logistics_cost),
            ref_type,
            ref_id
        ),
    )
    
    conn.commit()
    conn.close()


def insert_city(
    name: str,
    region: str = None,
    margin_per_unit: float = 5.0
) -> int:
    """
    Insert or get city_id for a city.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        "INSERT OR IGNORE INTO cities(name, region, margin_per_unit) VALUES (?, ?, ?)",
        (name, region, float(margin_per_unit))
    )
    conn.commit()
    
    cur.execute("SELECT id FROM cities WHERE name = ?", (name,))
    row = cur.fetchone()
    city_id = row["id"] if "id" in row.keys() else row[0]
    
    conn.close()
    return city_id


def insert_shipment(
    factory_id: int,
    city_id: int,
    qty: int,
    status: str = "IN_TRANSIT",
    truck_id: str = None
) -> int:
    """
    Insert a new shipment record.
    Returns shipment_id.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO shipments(
            factory_id, city_id, qty, departed_at, status, truck_id
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (factory_id, city_id, int(qty), _utc_now(), status, truck_id)
    )
    
    shipment_id = cur.lastrowid
    conn.commit()
    conn.close()
    return shipment_id


def update_shipment_arrival(
    shipment_id: int,
    status: str = "DELIVERED",
    transit_time_s: int = None,
    spoilage: int = 0
) -> None:
    """
    Update shipment when it arrives.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        UPDATE shipments
        SET arrived_at = ?, status = ?, transit_time_s = ?, spoilage = ?
        WHERE id = ?
        """,
        (_utc_now(), status, transit_time_s, int(spoilage), shipment_id)
    )
    
    conn.commit()
    conn.close()


__all__ = [
    "insert_global_event",
    "insert_profit_entry",
    "insert_city",
    "insert_shipment",
    "update_shipment_arrival",
]

def insert_transport_loss(
    shipment_id: int,
    lost_units: int,
    loss_value: float
) -> None:
    """
    Record transport spoilage and its financial impact.

    - Adds lost_units to shipments.spoilage
    - Writes a logistics_cost entry into profit_ledger
    """
    conn = get_connection()
    cur = conn.cursor()

    # 1) Update shipments.spoilage
    cur.execute(
        """
        UPDATE shipments
        SET spoilage = COALESCE(spoilage, 0) + ?
        WHERE id = ?
        """,
        (int(lost_units), int(shipment_id))
    )
    conn.commit()
    conn.close()

    # 2) Log as a logistics cost in profit_ledger
    # Look up factory_id from shipments table
    cur.execute("SELECT factory_id FROM shipments WHERE id = ?", (int(shipment_id),))
    row = cur.fetchone()
    factory_id = row[0] if row else None

    insert_profit_entry(
        factory_id=factory_id,
        city_id=None,
        revenue=0.0,
        cogs=0.0,
        event_cost=0.0,
        logistics_cost=float(loss_value),
        ref_type="transport_loss",
        ref_id=int(shipment_id),
    )


def insert_supervisor_action(
    factory_id: int,
    station_id: int = None,
    action_type: str = "worker_change",
    delta_workers: int = 0,
    reason: str = None,
    strategy_id: int = None
) -> None:
    """
    Log a supervisor decision/action.
    
    Args:
        factory_id: Factory where action occurred
        station_id: Station affected (if applicable)
        action_type: Type of action (worker_change, repair, etc.)
        delta_workers: Change in worker count (+1, -1, etc.)
        reason: Textual reason for decision
        strategy_id: Strategy that made decision (if tracked)
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO supervisor_actions(
            factory_id, station_id, action_type, delta_workers, reason, strategy_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (factory_id, station_id, action_type, int(delta_workers), reason, strategy_id, _utc_now())
    )
    
    conn.commit()
    conn.close()


__all__ = [
    "insert_global_event",
    "insert_profit_entry",
    "insert_city",
    "insert_shipment",
    "update_shipment_arrival",
    "insert_supervisor_action",  # Added
]


def insert_demand_snapshot(
    city_id: int,
    demand_rate_units_h: float,
    price: float = None,
    promo_flag: int = 0,
    model_version: str = None,
    extras: str = "{}"
) -> None:
    """
    Log a city demand snapshot.
    
    Args:
        city_id: City ID
        demand_rate_units_h: Demand rate in units per hour
        price: Price per unit (if tracked)
        promo_flag: 1 if promotion active, 0 otherwise
        model_version: Demand model version identifier
        extras: JSON with additional demand data
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO demand_snapshots(
            city_id, ts, demand_rate_units_h, price, promo_flag, model_version, extras
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (city_id, _utc_now(), float(demand_rate_units_h), price, int(promo_flag), model_version, extras)
    )
    
    conn.commit()
    conn.close()


def insert_routing_decision(
    policy_name: str,
    inputs: str,
    chosen_city_id: int,
    qty: int
) -> None:
    """
    Log a routing decision made by routing strategy.
    
    Args:
        policy_name: Name of routing strategy used
        inputs: JSON with decision inputs (distances, workloads, etc.)
        chosen_city_id: City assigned to order
        qty: Quantity routed
    """
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        INSERT INTO routing_decisions(
            ts, policy_name, inputs, chosen_city_id, qty
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (_utc_now(), policy_name, inputs, int(chosen_city_id), int(qty))
    )
    
    conn.commit()
    conn.close()


__all__ = [
    "insert_global_event",
    "insert_profit_entry",
    "insert_city",
    "insert_shipment",
    "update_shipment_arrival",
    "insert_transport_loss",
    "insert_supervisor_action",
    "insert_demand_snapshot",
    "insert_routing_decision",
]

