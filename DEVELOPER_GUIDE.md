# 🍫 Willy Wonka Chocolate Factory Simulation - Deep Dive Developer Guide

## 1. Project Overview
This project is a **multi-threaded, event-driven simulation** of a global chocolate manufacturing and logistics network. It models the entire lifecycle of chocolate production—from raw material processing in factories to final delivery in cities worldwide.

The system is designed to demonstrate **Operating Systems & Parallel Computing** concepts, including:
- **Concurrency**: Multiple background threads managing distinct subsystems (Simulation, Demand, Events, Database).
- **Synchronization**: Thread-safe queues and event handling.
- **Resource Management**: Finite factory capacity, worker allocation, and truck logistics.

---

## 2. System Architecture & Interactions

The application is built around a **Hub-and-Spoke** architecture where the `EventBus` acts as the central nervous system.

### Core Components
1.  **Simulation Loop (`core/simulation.py`)**: The heartbeat of the factory floor. It ticks every time step to process items through factory stations.
2.  **Demand Engine (`logistics/demand_engine.py`)**: A background thread that simulates global market demand, generates orders, and manages logistics (trucks).
3.  **Event Engine (`events/event_engine.py`)**: A probabilistic engine that injects random events (e.g., "Robbery", "Heatwave", "VIP Visit") to disrupt or boost operations.
4.  **Database Manager (`database/db_manager.py`)**: A centralized singleton that logs every metric, transaction, and event to a SQLite database for persistence and analysis.
5.  **Dashboard (`dashboard/`)**: A TUI (Text User Interface) built with `Textual` and `Rich` that visualizes the system state in real-time.

---

## 3. System Dynamics & Logic

### � Demand Dynamics
Demand is not static; it evolves based on **City Strategies** and **Global Events**.

#### City Strategies (`strategies/city_demand_strategy.py`)
Each city has a personality that dictates its chocolate preferences:
-   **CaramelLoverStrategy**: 2.0x demand for Caramel, 0.8x for others.
-   **HazelnutFocusedStrategy**: 2.0x demand for Hazelnut.
-   **NoisyCityDemandStrategy**: Demand fluctuates in sinusoidal waves (amplitude 0.3) + random noise (factor 0.2).
-   **BalancedDemandStrategy**: Stable demand with minimal fluctuation (±5%).

#### Demand → Orders
The `DemandEngine` runs every 3 seconds:
1.  Updates demand for all cities based on their strategy.
2.  Converts demand to **Order Probability**: `prob = min(0.8, demand / 20.0)`. High demand = high chance of order.
3.  **Order Quantity**: `quantity = demand * random(0.5, 1.5)`.

---

## 4. Event System Mechanics (`events/event_engine.py`)

The `EventEngine` wakes up every 8 seconds and has a **30% chance** to trigger an event.

### 🚨 Negative Events
1.  **Robbery (8%)**:
    -   **Trigger**: Probability scales with the number of **Golden Tickets** in production.
    -   **Effect**: Steals golden tickets from queues.
    -   **Defense**: Factories recently robbed get a temporary security boost (up to 95% protection).
2.  **Machine Breakdown (12%)**:
    -   **Effect**: A random station (e.g., "Molding") stops working for 5-15 seconds.
    -   **Cost**: Incurs a repair cost ($500-$1500).
3.  **Cocoa Shortage (10%)**:
    -   **Effect**: Global production costs multiply by **3x-5x** for 5-10 seconds.
    -   **Impact**: Massive temporary dip in profitability.

### ✨ Positive Events
1.  **VIP Visit (12%)**:
    -   **Trigger**: Favors factories with high **Efficiency** (Throughput / Defect Rate).
    -   **Effect**: Grants a **60-second Shield** that blocks all negative events (Robberies, Breakdowns).
2.  **Viral Campaign (12%)**:
    -   **Effect**: A specific bar type (e.g., "Dark") sees **2.5x - 4.0x** demand globally.
3.  **Holiday Rush (10%)**:
    -   **Effect**: All demand across all cities increases by **1.5x - 2.0x**.

---

## 5. Financial Model

The simulation tracks a detailed P&L (Profit and Loss) ledger in `factory.db`.

### Revenue
-   **Sales**: Revenue is recognized when an order is **DELIVERED**.
-   **Pricing**:
    -   Caramel: $15/bar
    -   Hazelnut: $16/bar
    -   Dark: $17/bar
    -   Milk: $14/bar

### Costs
-   **Production Cost**: Incurred when raw materials enter the pipeline ($9-$13/bar depending on factory efficiency).
-   **Wages**: $0.50 per worker per second.
-   **Breakdowns**: One-time repair costs ($500+).
-   **Cocoa Shortage**: Multiplies production costs by 3-5x during the event.

---

## 6. Concurrency Model

The application uses **Python `threading`** to run multiple operations in parallel:

1.  **Main Thread**: Runs the `Textual` dashboard UI. It must remain responsive, so it never blocks.
2.  **Simulation Thread**: Iterates through all factories and stations, moving items.
3.  **DemandEngine Thread**: Wakes up periodically to generate orders and move trucks.
4.  **EventEngine Thread**: Wakes up periodically to trigger random events.
5.  **DB Snapshot Thread**: Runs every 10 seconds to dump high-volume metrics (queue sizes, worker counts) to the database without slowing down the main simulation.

**Synchronization**:
-   We use **Thread-Safe Queues** (implied or explicit) for item passing between stations.
-   The `EventBus` handles cross-thread communication (e.g., DemandEngine thread telling the UI thread that a truck arrived).

---

## 7. Data Flow Example: The Life of a Chocolate Bar 🍫

1.  **Demand**: The `DemandEngine` calculates that **Paris** (Hazelnut Strategy) wants **Hazelnut** chocolate.
2.  **Order**: An `Order` is generated for 50 bars.
3.  **Routing**: The `BalancedRoutingStrategy` checks factories. **Wonka-Berlin** is closest and has capacity. Order is assigned to Berlin.
4.  **Production**:
    -   Wonka-Berlin's `backlog` increases.
    -   The `Simulation` thread sees the backlog and starts processing raw ingredients.
    -   Items flow: `Crushing` → `Molded` → `Filled` → `QC`.
5.  **Shipment**: Once produced, the `DemandEngine` marks the order as `IN_TRANSIT`. A truck (visualized in the dashboard) starts moving.
6.  **Delivery**: After the calculated travel time (distance / speed), the order arrives in Paris.
7.  **Logging**: The `DatabaseManager` records the shipment arrival, transit time, and revenue in `factory.db`.

---

## 8. How to Extend

### Adding a New Factory
1.  Open `main.py`.
2.  Add a new `Factory` instance to the `factories` list.
3.  Give it a unique `name` and `lat/lon` coordinates.
4.  The system automatically registers it in the DB and UI.

### Adding a New Event
1.  Open `events/event_engine.py`.
2.  Define a new method (e.g., `_cocoa_shortage`).
3.  Add it to the `EVENT_TYPES` list with a probability.
4.  Implement the logic (e.g., iterate through factories and reduce `efficiency`).

### Changing Logistics Logic
1.  Look at `strategies/routing_strategy.py`.
2.  Modify `assign_factory` to change how factories are chosen (e.g., prioritize cost over distance).
