from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, Mapping

from .db import get_connection


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> str:
    """Return current UTC time as ISO string with timezone."""
    return datetime.now(timezone.utc).isoformat()


def _get_or_create_factory_id(factory_name: str) -> int:
    """
    Ensure the given factory exists in the `factories` table and return its id.
    Shared by queues, stations and factory-level snapshots.
    """
    conn = get_connection()
    cur = conn.cursor()

    # Create if missing
    cur.execute(
        "INSERT OR IGNORE INTO factories(name) VALUES (?)",
        (factory_name,),
    )
    conn.commit()

    # Read id
    cur.execute(
        "SELECT id FROM factories WHERE name = ?",
        (factory_name,),
    )
    row = cur.fetchone()
    if row is None:
        conn.close()
        raise RuntimeError(f"Factory '{factory_name}' not found after insert.")

    factory_id = row["id"] if "id" in row.keys() else row[0]
    conn.close()
    return factory_id


# ---------------------------------------------------------------------------
# Queue registration + snapshots
# ---------------------------------------------------------------------------


def register_factory_queues(
    factory_name: str,
    queue_defs: Mapping[str, int],
) -> Dict[str, int]:
    """
    Register the queues of a factory in the `queues` table.

    Parameters
    ----------
    factory_name:
        Name of the factory (e.g. 'WonkaFactory').
    queue_defs:
        Mapping of logical queue name -> max_size, for example:
        {"Crushed": 10, "Molded": 10, "Filled": 10}

    Returns
    -------
    dict
        Mapping logical queue name -> queue_id in the DB.
    """
    factory_id = _get_or_create_factory_id(factory_name)

    conn = get_connection()
    cur = conn.cursor()

    ids: Dict[str, int] = {}

    for q_name, max_size in queue_defs.items():
        cur.execute(
            """
            INSERT INTO queues(factory_id, max_size)
            VALUES (?, ?)
            """,
            (factory_id, int(max_size)),
        )
        ids[q_name] = cur.lastrowid

    conn.commit()
    conn.close()
    return ids


def insert_queue_snapshot(
    queue_id: int,
    size: int,
    blocked: int = 0,
    dropped: int = 0,
) -> None:
    """
    Insert a single row into `queue_snapshots`.

    Called from BoundedQueue.push()/pop().
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO queue_snapshots(queue_id, ts, size, blocked, dropped)
        VALUES (?, ?, ?, ?, ?)
        """,
        (queue_id, _utc_now(), int(size), int(blocked), int(dropped)),
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Station registration + snapshots
# ---------------------------------------------------------------------------

# Order along the pipeline – tweak if your pipeline changes.
STATION_PIPELINE_ORDER = {
    "Crushing": 1,
    "Molding": 2,
    "Filling": 3,
    "QC": 4,
    "Boxing": 5,
}


def register_factory_stations(
    factory_name: str,
    station_kinds: Mapping[str, str],
) -> Dict[str, int]:
    """
    Register the stations of a factory in `station_types` + `factory_stations`.

    Parameters
    ----------
    factory_name:
        Name of the factory (e.g. 'WonkaFactory').
    station_kinds:
        Mapping of *station instance name* -> *logical kind*, for example:
        {
            "WonkaFactory-Crushing": "Crushing",
            "WonkaFactory-Molding": "Molding",
            ...
        }

    Returns
    -------
    dict
        Mapping station instance name -> factory_stations.id in the DB.
    """
    factory_id = _get_or_create_factory_id(factory_name)

    conn = get_connection()
    cur = conn.cursor()

    # 1) Ensure station_types rows exist for all kinds we use
    for kind in set(station_kinds.values()):
        order = STATION_PIPELINE_ORDER.get(kind, 99)
        cur.execute(
            """
            INSERT OR IGNORE INTO station_types(name, pipeline_order)
            VALUES (?, ?)
            """,
            (kind, order),
        )

    conn.commit()

    # 2) Fetch type ids into a dict
    cur.execute("SELECT id, name FROM station_types")
    type_ids: Dict[str, int] = {}
    for row in cur.fetchall():
        name = row["name"] if "name" in row.keys() else row[1]
        _id = row["id"] if "id" in row.keys() else row[0]
        type_ids[name] = _id

    # 3) Create factory_stations rows
    station_ids: Dict[str, int] = {}
    for station_name, kind in station_kinds.items():
        type_id = type_ids[kind]
        # capacity=1 is fine; real capacity is handled in code, this is metadata
        cur.execute(
            """
            INSERT INTO factory_stations(factory_id, station_type_id, capacity, active)
            VALUES (?, ?, ?, 1)
            """,
            (factory_id, type_id, 1),
        )
        station_ids[station_name] = cur.lastrowid

    conn.commit()
    conn.close()
    return station_ids


def insert_station_snapshot(
    station_id: int,
    workers: int,
    utilization: float,
    faulted: bool,
    avg_latency_ms: int | None = None,
) -> None:
    """
    Insert a row into `station_snapshots`.

    Called from Factory.get_station_metrics().
    """
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO station_snapshots(
            station_id, ts, workers, utilization, faulted, avg_latency_ms
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            station_id,
            _utc_now(),
            int(workers),
            float(utilization),
            1 if faulted else 0,
            int(avg_latency_ms) if avg_latency_ms is not None else None,
        ),
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Factory snapshots (NEW)
# ---------------------------------------------------------------------------


def insert_factory_snapshot(
    factory_name: str,
    throughput_1m: int,
    wip: int,
    defect_rate: float,
    cash: float,
) -> None:
    """
    Insert a row into `factory_snapshots`.

    `cash` here can be interpreted as current cash/profit for the factory.
    """
    factory_id = _get_or_create_factory_id(factory_name)

    conn = get_connection()
    cur = conn.cursor()

    cur.execute(
        """
        INSERT INTO factory_snapshots(
            factory_id, ts, throughput_1m, wip, defect_rate, cash
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            factory_id,
            _utc_now(),
            int(throughput_1m),
            int(wip),
            float(defect_rate),
            float(cash),
        ),
    )

    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# _get_or_create_factory_id helper (exported for db_manager)
# ---------------------------------------------------------------------------

# Already defined above, just adding to exports

__all__ = [
    "register_factory_queues",
    "insert_queue_snapshot",
    "register_factory_stations",
    "insert_station_snapshot",
    "insert_factory_snapshot",
    "_get_or_create_factory_id",  # For db_manager
]
