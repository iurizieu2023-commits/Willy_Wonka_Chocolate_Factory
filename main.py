# main.py - Geographic Logistics Version

import random
import threading
import time  # Added by user

from observers.event_bus import EventBus
from core.factory import Factory
from core.simulation import Simulation
from dashboard.textual_dashboard import run_textual_dashboard
from events.event_engine import EventEngine
from utils.colors import Color
import global_state
from logistics.city import City
from logistics.demand_engine import DemandEngine
from strategies.city_demand_strategy import (
    NoisyCityDemandStrategy,
    CaramelLoverStrategy,
    HazelnutFocusedStrategy,
    BalancedDemandStrategy,
    # DarkChocolateLoverStrategy  # Not used in the provided snippet, keeping original
)
from strategies.routing_strategy import BalancedRoutingStrategy
from strategies.aggressive_supervisor import AggressiveSupervisor
from strategies.filling_strategy import WeightedFillingStrategy  # Added by user

# Phase 13: Database logging
ENABLE_DATABASE = True  # Toggle database logging on/off

if ENABLE_DATABASE:
    from database.db_manager import get_db_manager

# NEW: auto DB report
from database.report import print_run_summary


def run_simulation_logic(
    simulation: Simulation,
    event_bus: EventBus,
    demand_engine: DemandEngine,
    cities,
) -> None:
    """Run simulation logic in background thread."""
    # CRITICAL FIX: Set cities BEFORE EventEngine starts!
    global_state.cities = cities

    # Start event engine
    event_engine = EventEngine(event_bus, factories=simulation.factories)
    event_engine.start()

    # Start demand engine
    demand_engine.start()

    print(
        f"{Color.BOLD}=== Starting simulation with {len(simulation.factories)} factories, "
        f"{len(cities)} cities ==={Color.RESET}"
    )

    # Start simulation
    simulation.start_all()


def main() -> None:
    event_bus = EventBus()

    # Phase 11: 12 Cities - mix of factory-cities and remote cities
    cities = [
        # Cities with local factories
        City("London", 51.51, -0.13, CaramelLoverStrategy()),
        City("Paris", 48.86, 2.35, HazelnutFocusedStrategy()),
        City("New York", 40.71, -74.01, NoisyCityDemandStrategy()),
        City("Tokyo", 35.68, 139.69, BalancedDemandStrategy()),
        City("Sydney", -33.87, 151.21, CaramelLoverStrategy()),
        City("São Paulo", -23.55, -46.63, HazelnutFocusedStrategy()),
        # Remote cities (no local factory - demonstrates routing)
        City("Berlin", 52.52, 13.40, NoisyCityDemandStrategy()),        # → Paris/London
        City("Madrid", 40.42, -3.70, BalancedDemandStrategy()),         # → Paris/London
        City("Toronto", 43.65, -79.38, CaramelLoverStrategy()),         # → NewYork
        City("Mexico City", 19.43, -99.13, HazelnutFocusedStrategy()),  # → NewYork/Brazil
        City("Singapore", 1.35, 103.82, NoisyCityDemandStrategy()),     # → Tokyo
        City("Mumbai", 19.08, 72.88, BalancedDemandStrategy()),         # → Tokyo (far!)
    ]

    # Phase 11: Factories strategically located
    simulation = Simulation(event_bus)

    factories = [
        Factory(
            name="Wonka-London",
            event_bus=event_bus,
            lat=51.51,
            lon=-0.13,  # London
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
        Factory(
            name="Wonka-Paris",
            event_bus=event_bus,
            lat=48.86,
            lon=2.35,  # Paris
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
        Factory(
            name="Wonka-NewYork",
            event_bus=event_bus,
            lat=40.71,
            lon=-74.01,  # New York
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
        Factory(
            name="Wonka-Tokyo",
            event_bus=event_bus,
            lat=35.68,
            lon=139.69,  # Tokyo
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
        Factory(
            name="Wonka-Brazil",
            event_bus=event_bus,
            lat=-23.55,
            lon=-46.63,  # São Paulo
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
        Factory(
            name="Wonka-LosAngeles",
            event_bus=event_bus,
            lat=34.05,
            lon=-118.24,  # Los Angeles
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
        Factory(
            name="Wonka-Shanghai",
            event_bus=event_bus,
            lat=31.23,
            lon=121.47,  # Shanghai
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
        Factory(
            name="Wonka-Cairo",
            event_bus=event_bus,
            lat=30.04,
            lon=31.23,  # Cairo
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
        Factory(
            name="Wonka-Moscow",
            event_bus=event_bus,
            lat=55.75,
            lon=37.61,  # Moscow
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
        Factory(
            name="Wonka-BuenosAires",
            event_bus=event_bus,
            lat=-34.60,
            lon=-58.38,  # Buenos Aires
            items_to_produce=40,
            queue_capacity=10,
            enable_filling=True,
        ),
    ]

    # Add all factories
    for factory in factories:
        simulation.add_factory(factory)

    global_state.factory_ids = [f.name for f in factories]

    # Set supervisor strategy
    simulation.set_supervisor_strategy(AggressiveSupervisor())

    # Phase 13: Initialize database manager FIRST
    db_manager = None
    if ENABLE_DATABASE:
        db_manager = get_db_manager(enable_logging=True)

        # Register all factories
        for factory in factories:
            db_manager.register_factory(factory)
            # Pass db_manager to factory for per-item logging
            factory._db_manager = db_manager

        # Register all cities
        for city in cities:
            db_manager.register_city(city, region="World")

        # Subscribe to events for logging
        def log_event_to_db(event_type, event_data):
            if event_type == "global_event":
                db_manager.log_event(event_data)

        event_bus.subscribe("global_event", log_event_to_db)

        # Periodic snapshot logging (factory, station, queues)
        def log_snapshots():
            import time

            while True:
                time.sleep(10)  # Log every 10 seconds
                for factory in factories:
                    # Factory snapshot
                    db_manager.log_factory_snapshot(factory)

                    # Station snapshots
                    for station in factory.stations:
                        db_manager.log_station_snapshot(factory, station)

                    # Queue snapshots (Phase 13)
                    try:
                        from database.insertions import insert_queue_snapshot

                        for queue_name in ["Crushed", "Molded", "Filled", "QC"]:
                            queue_key = f"{factory.name}-{queue_name}"
                            queue_id = db_manager.queue_ids.get(queue_key)
                            if queue_id:
                                if (
                                    queue_name == "Crushed"
                                    and hasattr(factory, "q_crushed")
                                ):
                                    insert_queue_snapshot(
                                        queue_id, factory.q_crushed.size()
                                    )
                                elif (
                                    queue_name == "Molded"
                                    and hasattr(factory, "q_molded")
                                ):
                                    insert_queue_snapshot(
                                        queue_id, factory.q_molded.size()
                                    )
                                elif (
                                    queue_name == "Filled"
                                    and hasattr(factory, "q_filled")
                                ):
                                    insert_queue_snapshot(
                                        queue_id, factory.q_filled.size()
                                    )
                                elif (
                                    queue_name == "QC"
                                    and hasattr(factory, "q_qc")
                                ):
                                    insert_queue_snapshot(
                                        queue_id, factory.q_qc.size()
                                    )
                    except Exception as e:
                        print(f"Error logging snapshots: {e}")

        snapshot_thread = threading.Thread(
            target=log_snapshots,
            daemon=True,
            name="DB-Snapshots",
        )
        snapshot_thread.start()

        # Pass db_manager to supervisor
        if hasattr(simulation, "supervisor") and simulation.supervisor:
            simulation.supervisor.db_manager = db_manager

        print(f"{Color.GREEN}✅ Database logging enabled{Color.RESET}")

    # Phase 11: DemandEngine with BalancedRouting
    demand_engine = DemandEngine(
        event_bus=event_bus,
        cities=cities,
        factories=factories,
        period=3.0,  # Update every 3s
        order_rate=0.6,  # 60% chance per city per cycle (higher for more activity)
        routing_strategy=BalancedRoutingStrategy(
            proximity_weight=0.6,
            workload_weight=0.4,
        ),
        db_manager=db_manager,  # Phase 13: Pass for shipment logging
    )
    print(
        f"{Color.CYAN}DEBUG: DemandEngine initialized with {len(factories)} factories, "
        f"{len(cities)} cities{Color.RESET}"
    )
    global_state.demand_engine = demand_engine

    # Start simulation in background thread
    sim_thread = threading.Thread(
        target=run_simulation_logic,
        args=(simulation, event_bus, demand_engine, cities),  # Pass cities!
        daemon=True,
        name="SimulationLogic",
    )
    sim_thread.start()

    # Launch dashboard with cities and demand engine for truck animation
    run_textual_dashboard(
        simulation,
        factories,
        event_bus,
        cities=cities,
        demand_engine=demand_engine,
    )

    # Cleanup
    print(f"{Color.YELLOW}Dashboard closed, shutting down...{Color.RESET}")
    demand_engine.stop()
    simulation.shutdown_all()

    # IMPORTANT: print report BEFORE closing DB
    if db_manager is not None:
        try:
            print_run_summary(db_manager)
        except Exception as e:
            print(
                f"{Color.RED}Run summary disabled "
                f"(DB error: {e}){Color.RESET}"
            )
        db_manager.close()

    print(f"{Color.GREEN}Simulation finished.{Color.RESET}")


if __name__ == "__main__":
    main()
