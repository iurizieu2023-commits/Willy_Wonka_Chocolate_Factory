# database/report.py

import sqlite3
from utils.colors import Color


def _get_connection_from_db_manager(db_manager: object) -> sqlite3.Connection:
    """
    Try to locate the sqlite3.Connection inside DBManager without
    depending on a specific attribute name.

    We first look for known attribute names (conn, _conn, connection, _connection),
    then fall back to scanning all attributes for a sqlite3.Connection instance.
    """
    # 1) Known/common attribute names
    for attr in ("conn", "_conn", "connection", "_connection"):
        value = getattr(db_manager, attr, None)
        if isinstance(value, sqlite3.Connection):
            return value

    # 2) Fallback: scan all attributes and pick the first sqlite3.Connection
    for value in db_manager.__dict__.values():
        if isinstance(value, sqlite3.Connection):
            return value

    raise AttributeError("DBManager has no sqlite3.Connection attribute")


def print_run_summary(db_manager: object) -> None:
    """
    Print a small end-of-run report using ONLY the SQLite DB.

    It:
      - Lists factories (if table exists)
      - Summarises global events by type (if table exists)
      - Summarises station snapshot samples (if table exists)

    All queries are wrapped in try/except so missing tables or columns
    never crash the simulation; they just show a friendly message.
    """
    try:
        conn = _get_connection_from_db_manager(db_manager)
    except Exception as e:
        print(
            f"{Color.RED}Run summary disabled (DB error: {e}){Color.RESET}"
        )
        return

    cur = conn.cursor()

    print()
    print(f"{Color.GREEN}=== END OF REPORT ==={Color.RESET}")

    # Discover which tables actually exist
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = {row[0] for row in cur.fetchall()}

    # ------------------------------------------------------------------
    # 1) FACTORIES
    # ------------------------------------------------------------------
    try:
        if "factories" in tables:
            print(f"{Color.BOLD}\nFactories (from DB):{Color.RESET}")
            cur.execute("SELECT id, name FROM factories ORDER BY id")
            rows = cur.fetchall()
            for fid, name in rows:
                print(f"  - [{fid}] {name}")
            print(f"  Total factories: {len(rows)}")
        else:
            print("Factories table not found in DB.")
    except Exception as e:
        print(f"Factory summary error: {e}")

    # ------------------------------------------------------------------
    # 2) GLOBAL EVENTS / BREAKDOWNS
    # ------------------------------------------------------------------
    try:
        if "global_events" in tables:
            print(f"{Color.BOLD}\nGlobal events (from DB):{Color.RESET}")

            # Check available columns
            cur.execute("PRAGMA table_info(global_events)")
            cols = [c[1] for c in cur.fetchall()]

            if "type" in cols:
                cur.execute(
                    """
                    SELECT type, COUNT(*) 
                    FROM global_events 
                    GROUP BY type 
                    ORDER BY COUNT(*) DESC
                    """
                )
                rows = cur.fetchall()
                if rows:
                    for evt_type, count in rows:
                        print(f"  - {evt_type}: {count}")
                else:
                    print("  (no events logged)")
            else:
                cur.execute("SELECT COUNT(*) FROM global_events")
                total = cur.fetchone()[0]
                print(f"  Total events: {total}")
        else:
            print("Global events table not found in DB.")
    except Exception as e:
        print(f"Breakdown summary error: {e}")

    # ------------------------------------------------------------------
    # 3) STATION STRESS / FAULT SNAPSHOTS
    # ------------------------------------------------------------------
    try:
        if "station_snapshots" in tables:
            print(f"{Color.BOLD}\nStation snapshots (from DB):{Color.RESET}")

            cur.execute("PRAGMA table_info(station_snapshots)")
            cols = [c[1] for c in cur.fetchall()]

            if "faulted" in cols:
                cur.execute(
                    """
                    SELECT 
                        SUM(CASE WHEN faulted THEN 1 ELSE 0 END) AS faulted_samples,
                        COUNT(*) AS total_samples
                    FROM station_snapshots
                    """
                )
                faulted, total = cur.fetchone()
                faulted = faulted or 0
                total = total or 0
                print(f"  Samples: {total} (faulted: {faulted})")
            else:
                cur.execute("SELECT COUNT(*) FROM station_snapshots")
                total = cur.fetchone()[0]
                print(f"  Samples: {total}")
        else:
            print("Station snapshots table not found in DB.")
    except Exception as e:
        print(f"Stress summary error: {e}")

    print()  # final blank line
