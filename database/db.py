import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "factory.db")


def get_connection():
    """Returns a SQLite connection with the correct PRAGMA settings."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Required PRAGMAs
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")

    return conn


def initialize_database():
    """Creates all tables according to the official factory SQL specification."""
    conn = get_connection()
    cursor = conn.cursor()

    # ----------------------------
    # 1) REFERENCE / CONFIGURATION
    # ----------------------------
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS factories (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        location TEXT
    );

    CREATE TABLE IF NOT EXISTS station_types (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        pipeline_order INTEGER NOT NULL
    );

    CREATE TABLE IF NOT EXISTS strategies (
        id INTEGER PRIMARY KEY,
        scope TEXT NOT NULL,
        name TEXT NOT NULL,
        params TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(params))
    );

    CREATE TABLE IF NOT EXISTS factory_stations (
        id INTEGER PRIMARY KEY,
        factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE,
        station_type_id INTEGER NOT NULL REFERENCES station_types(id),
        capacity INTEGER NOT NULL DEFAULT 1,
        strategy_id INTEGER REFERENCES strategies(id),
        active INTEGER NOT NULL DEFAULT 1
    );

    CREATE TABLE IF NOT EXISTS queues (
        id INTEGER PRIMARY KEY,
        factory_id INTEGER NOT NULL REFERENCES factories(id) ON DELETE CASCADE,
        from_station_id INTEGER REFERENCES factory_stations(id),
        to_station_id INTEGER REFERENCES factory_stations(id),
        max_size INTEGER NOT NULL
    );
    """)

    # ----------------------------
    # 2) ITEMS & PRODUCTION
    # ----------------------------
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS batches (
        id INTEGER PRIMARY KEY,
        factory_id INTEGER NOT NULL REFERENCES factories(id),
        planned_qty INTEGER,
        recipe TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(recipe)),
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY,
        batch_id INTEGER NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL,
        attrs TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(attrs)),
        golden_ticket INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS item_transitions (
        id INTEGER PRIMARY KEY,
        item_id INTEGER NOT NULL REFERENCES items(id) ON DELETE CASCADE,
        factory_id INTEGER NOT NULL REFERENCES factories(id),
        station_id INTEGER NOT NULL REFERENCES factory_stations(id),
        status TEXT NOT NULL,
        entered_at TEXT,
        exited_at TEXT,
        cycle_time_ms INTEGER,
        temperature REAL,
        defect_code TEXT,
        notes TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_trans_item ON item_transitions(item_id);
    CREATE INDEX IF NOT EXISTS idx_trans_station_time ON item_transitions(station_id, entered_at);
    """)

    # ----------------------------
    # DEFECT LOG
    # ----------------------------
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS defect_log (
        id INTEGER PRIMARY KEY,
        item_id INTEGER REFERENCES items(id),
        batch_id INTEGER REFERENCES batches(id),
        station_id INTEGER REFERENCES factory_stations(id),
        defect_type TEXT NOT NULL,
        severity INTEGER NOT NULL,
        detected_at TEXT NOT NULL,
        reworked INTEGER NOT NULL DEFAULT 0
    );
    """)

    # ----------------------------
    # 3) RUNTIME SNAPSHOTS
    # ----------------------------
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS queue_snapshots (
        id INTEGER PRIMARY KEY,
        queue_id INTEGER NOT NULL REFERENCES queues(id),
        ts TEXT NOT NULL,
        size INTEGER NOT NULL,
        blocked INTEGER NOT NULL DEFAULT 0,
        dropped INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_qsnap_q_time ON queue_snapshots(queue_id, ts);

    CREATE TABLE IF NOT EXISTS station_snapshots (
        id INTEGER PRIMARY KEY,
        station_id INTEGER NOT NULL REFERENCES factory_stations(id),
        ts TEXT NOT NULL,
        workers INTEGER NOT NULL,
        utilization REAL,
        faulted INTEGER NOT NULL DEFAULT 0,
        avg_latency_ms INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_ssnap_s_time ON station_snapshots(station_id, ts);

    CREATE TABLE IF NOT EXISTS factory_snapshots (
        id INTEGER PRIMARY KEY,
        factory_id INTEGER NOT NULL REFERENCES factories(id),
        ts TEXT NOT NULL,
        throughput_1m INTEGER,
        wip INTEGER,
        defect_rate REAL,
        cash REAL
    );

    CREATE INDEX IF NOT EXISTS idx_fsnap_f_time ON factory_snapshots(factory_id, ts);
    """)

    # ----------------------------
    # GENERIC METRICS STREAM
    # ----------------------------
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS metric_stream (
        id INTEGER PRIMARY KEY,
        ts TEXT NOT NULL,
        entity_type TEXT NOT NULL,
        entity_id INTEGER NOT NULL,
        metric_name TEXT NOT NULL,
        value REAL,
        dims TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(dims))
    );

    CREATE INDEX IF NOT EXISTS idx_metric_entity_time ON metric_stream(entity_type, entity_id, ts);
    """)

    # ----------------------------
    # 4) SUPERVISOR & FAULTS
    # ----------------------------
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS supervisor_actions (
        id INTEGER PRIMARY KEY,
        factory_id INTEGER NOT NULL REFERENCES factories(id),
        station_id INTEGER REFERENCES factory_stations(id),
        action_type TEXT NOT NULL,
        delta_workers INTEGER,
        reason TEXT,
        strategy_id INTEGER REFERENCES strategies(id),
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS fault_events (
        id INTEGER PRIMARY KEY,
        factory_id INTEGER NOT NULL REFERENCES factories(id),
        station_id INTEGER REFERENCES factory_stations(id),
        type TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        severity INTEGER,
        payload TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(payload)),
        cost_impact REAL
    );
    """)

    # ----------------------------
    # 5) DEMAND / CITIES / LOGISTICS
    # ----------------------------
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS cities (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        region TEXT,
        margin_per_unit REAL NOT NULL,
        distance_km TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(distance_km))
    );

    CREATE TABLE IF NOT EXISTS demand_snapshots (
        id INTEGER PRIMARY KEY,
        city_id INTEGER NOT NULL REFERENCES cities(id),
        ts TEXT NOT NULL,
        demand_rate_units_h REAL NOT NULL,
        price REAL,
        promo_flag INTEGER NOT NULL DEFAULT 0,
        model_version TEXT,
        extras TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(extras))
    );

    CREATE TABLE IF NOT EXISTS shipments (
        id INTEGER PRIMARY KEY,
        factory_id INTEGER NOT NULL REFERENCES factories(id),
        city_id INTEGER NOT NULL REFERENCES cities(id),
        qty INTEGER NOT NULL,
        departed_at TEXT NOT NULL,
        arrived_at TEXT,
        status TEXT NOT NULL,
        truck_id TEXT,
        transit_time_s INTEGER,
        spoilage INTEGER NOT NULL DEFAULT 0
    );

    CREATE INDEX IF NOT EXISTS idx_ship_city_time ON shipments(city_id, departed_at);
    CREATE INDEX IF NOT EXISTS idx_ship_factory_time ON shipments(factory_id, departed_at);

    CREATE TABLE IF NOT EXISTS city_inventory (
        id INTEGER PRIMARY KEY,
        city_id INTEGER NOT NULL REFERENCES cities(id),
        ts TEXT NOT NULL,
        on_hand INTEGER NOT NULL,
        backorder INTEGER NOT NULL
    );

    CREATE INDEX IF NOT EXISTS idx_cityinv_city_time ON city_inventory(city_id, ts);

    CREATE TABLE IF NOT EXISTS routing_decisions (
        id INTEGER PRIMARY KEY,
        ts TEXT NOT NULL,
        policy_name TEXT NOT NULL,
        inputs TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(inputs)),
        chosen_city_id INTEGER NOT NULL REFERENCES cities(id),
        qty INTEGER NOT NULL
    );
    """)

    # ----------------------------
    # 6) GLOBAL EVENTS
    # ----------------------------
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS global_events (
        id INTEGER PRIMARY KEY,
        ts TEXT NOT NULL,
        type TEXT NOT NULL,
        scope TEXT NOT NULL,
        factory_id INTEGER REFERENCES factories(id),
        city_id INTEGER REFERENCES cities(id),
        station_id INTEGER REFERENCES factory_stations(id),
        effect TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(effect)),
        ttl_s INTEGER
    );

    CREATE TABLE IF NOT EXISTS event_impacts (
        id INTEGER PRIMARY KEY,
        event_id INTEGER NOT NULL REFERENCES global_events(id) ON DELETE CASCADE,
        metric TEXT NOT NULL,
        delta REAL NOT NULL,
        starts_at TEXT NOT NULL,
        ends_at TEXT
    );
    """)

    # ----------------------------
    # 7) FINANCIAL LEDGER
    # ----------------------------
    cursor.executescript("""
    CREATE TABLE IF NOT EXISTS profit_ledger (
        id INTEGER PRIMARY KEY,
        ts TEXT NOT NULL,
        factory_id INTEGER,
        city_id INTEGER,
        revenue REAL NOT NULL DEFAULT 0,
        cogs REAL NOT NULL DEFAULT 0,
        event_cost REAL NOT NULL DEFAULT 0,
        logistics_cost REAL NOT NULL DEFAULT 0,
        profit REAL GENERATED ALWAYS AS (revenue - cogs - event_cost - logistics_cost),
        ref_type TEXT,
        ref_id INTEGER
    );

    CREATE INDEX IF NOT EXISTS idx_profit_time ON profit_ledger(ts);
    """)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    print("Initializing database schema...")
    initialize_database()
    print("Database created at:", DB_PATH)
