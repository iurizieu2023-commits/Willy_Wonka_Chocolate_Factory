from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, DataTable, Static, Log, TabbedContent, TabPane
from textual.containers import Container
from textual.reactive import reactive
from rich.text import Text
import time
import threading


class WonkaDashboard(App):
    """
    Phase 8-10: Tabbed Textual dashboard for multi-factory simulation.
    
    Tabs:
    - Tab 1 (Overview): Factory table + Events table + Event log
    - Tab 2 (Factories): Detailed factory metrics
    - Tab 3 (Stations): All stations across all factories
    - Tab 4 (Cities): Cities & logistics (Phase 11)
    - Tab 5 (Financials): Financial performance (Phase 13)
    """

    CSS = """
    Screen {
        layout: vertical;
    }
    
    TabbedContent {
        height: 1fr;
    }
    
    DataTable {
        height: 1fr;
        border: solid purple;
    }

    Log {
        height: 1fr;
        border: solid green;
        background: $surface;
    }
    
    .status-working {
        color: green;
    }
    
    .status-idle {
        color: gray;
    }
    
    .status-blocked {
        color: red;
        text-style: bold;
    }
    
    .status-finished {
        color: blue;
    }

    #shutdown_overlay {
        background: black;
        color: yellow;
        text-style: bold;
        padding: 1 2;
        height: auto;
    }
    """

    BINDINGS = [
        ("q", "request_shutdown", "Quit"),
        ("1", "switch_tab('overview')", "Overview"),
        ("2", "switch_tab('factories')", "Factories"),
        ("3", "switch_tab('stations')", "Stations"),
        ("4", "switch_tab('cities')", "Cities"),
        ("5", "switch_tab('financials')", "Financials"),  # Phase 13
    ]

    def __init__(
        self,
        simulation,
        factories: list,
        event_bus,
        cities: list = None,
        demand_engine=None,  # Phase 11: For delivery truck animation
        supervisor=None,
        event_engine=None,
    ):
        super().__init__()
        self.simulation = simulation
        self.factories = factories
        self.cities = cities or []
        self.demand_engine = demand_engine  # Phase 11: Store for truck rendering
        self.event_bus = event_bus
        self.supervisor = supervisor
        self.event_engine = event_engine

        # Flag so we stop updating UI / reacting to events once shutdown starts
        self._shutdown_requested = False

    # ------------------------------------------------------------
    # COMPOSE
    # ------------------------------------------------------------
    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        
        # Phase 8-10: Tabbed content
        with TabbedContent(initial="overview"):
            # Tab 1: Overview (factories + events + log)
            with TabPane("Overview", id="overview"):
                yield DataTable(id="overview_table")
                # Global events table
                yield DataTable(id="events_table")
                # Log (mainly for golden tickets, etc.)
                yield Log(id="overview_log")
            
            # Tab 2: Factories
            with TabPane("Factories", id="factories"):
                yield DataTable(id="factories_table")
            
            # Tab 3: Stations
            with TabPane("Stations", id="stations"):
                yield DataTable(id="stations_table")
            
            # Tab 4: Cities & Logistics (Phase 11)
            with TabPane("Cities", id="cities"):
                yield Static(id="cities_content")
            
            # Tab 5: Financials (Phase 13)
            with TabPane("Financials", id="financials"):
                yield Static(id="financials_content")
        
        # Shutdown overlay at the bottom
        overlay = Static("", id="shutdown_overlay")
        overlay.display = False 
        yield overlay

        yield Footer()

    # ------------------------------------------------------------
    # MOUNT / SETUP
    # ------------------------------------------------------------
    def on_mount(self) -> None:
        # Setup Overview tab
        self._setup_overview_tab()
        # Events table
        self._setup_events_table()
        
        # Setup Factories tab
        self._setup_factories_tab()
        
        # Setup Stations tab
        self._setup_stations_tab()
        
        # Update all tabs periodically
        self.set_interval(0.25, self.update_all_tabs)

        # Subscribe to events for event log & events table
        self.event_bus.subscribe_all(self.handle_simulation_event)

    def _setup_overview_tab(self) -> None:
        """Setup Tab 1: Overview (factory summary table)."""
        table = self.query_one("#overview_table", DataTable)
        table.add_columns(
            "Factory", 
            "Boxed", 
            "Crushed Q", 
            "Molded Q", 
            "Filled Q", 
            "Crushing", 
            "Molding", 
            "Filling", 
            "Boxing"
        )
        
        for factory in self.factories:
            table.add_row(*self._get_overview_row(factory), key=factory.name)

    def _setup_events_table(self) -> None:
        """Setup the global events table shown in the Overview tab."""
        events_table = self.query_one("#events_table", DataTable)
        events_table.add_columns(
            "Time",
            "Type",
            "Factory/City",
            "Station",
            "Summary",
        )

    def _setup_factories_tab(self) -> None:
        """Setup Tab 2: Factories (detailed metrics)."""
        table = self.query_one("#factories_table", DataTable)
        table.add_columns(
            "Factory",
            "Boxed",
            "WIP",
            "Defect %",
            "Throughput/min",
            "Backlog",  # Phase 11: Changed from legacy 'Demand' to show actual backlog
            "Crushed Q",
            "Molded Q",
            "Filled Q"
        )
        
        for factory in self.factories:
            table.add_row(*self._get_factories_row(factory), key=f"fact_{factory.name}")

    def _setup_stations_tab(self) -> None:
        """Setup Tab 3: Stations (all stations grid)."""
        table = self.query_one("#stations_table", DataTable)
        table.add_columns(
            "Station",
            "Factory",
            "Activity",
            "In Q",
            "Out Q",
            "Workers",
            "Util %",
            "Stress",
            "Faulted?"
        )

    # ------------------------------------------------------------
    # PERIODIC UPDATES
    # ------------------------------------------------------------
    def update_all_tabs(self) -> None:
        """Update all tabs."""
        if self._shutdown_requested:
            return
        self.update_overview_tab()
        self.update_factories_tab()
        self.update_stations_tab()
        self.update_cities_tab()      # Phase 11
        self.update_financials_tab()  # Phase 13
    
    def update_cities_tab(self) -> None:
        """Update Cities & Logistics tab (Phase 11)."""
        if not self.cities or self._shutdown_requested:
            return
        
        try:
            from dashboard.cities_tab import render_cities_tab
            cities_content = self.query_one("#cities_content", Static)
            
            # Pass demand_engine for truck animation
            demand_engine = getattr(self, 'demand_engine', None)
            renderable = render_cities_tab(self.cities, self.factories, demand_engine)
            cities_content.update(renderable)
        except Exception:
            # Silently skip if cities_tab not available
            pass
    
    def update_financials_tab(self) -> None:
        """Update Tab 5: Financials (Phase 13)."""
        if self._shutdown_requested:
            return
        try:
            from dashboard.financials_tab import render_financials_tab
            financials_content = self.query_one("#financials_content", Static)
            renderable = render_financials_tab(self.factories)
            financials_content.update(renderable)
        except Exception:
            # Silently skip if financials_tab not available
            pass

    def update_overview_tab(self) -> None:
        """Update Tab 1: Overview."""
        table = self.query_one("#overview_table", DataTable)
        col_keys = list(table.columns.keys())
        
        for factory in self.factories:
            row = self._get_overview_row(factory)
            for col_idx, value in enumerate(row):
                table.update_cell(factory.name, col_keys[col_idx], value)

    def update_factories_tab(self) -> None:
        """Update Tab 2: Factories."""
        table = self.query_one("#factories_table", DataTable)
        col_keys = list(table.columns.keys())
        
        for factory in self.factories:
            row = self._get_factories_row(factory)
            row_key = f"fact_{factory.name}"
            
            # Add row if not exists
            if row_key not in table.rows:
                table.add_row(*row, key=row_key)
            else:
                for col_idx, value in enumerate(row):
                    table.update_cell(row_key, col_keys[col_idx], value)

    def update_stations_tab(self) -> None:
        """Update Tab 3: Stations."""
        table = self.query_one("#stations_table", DataTable)
        col_keys = list(table.columns.keys())
        
        # Clear and rebuild (simpler than tracking changes)
        table.clear()
        
        for factory in self.factories:
            metrics_list = factory.get_station_metrics()
            for metrics in metrics_list:
                row = [
                    metrics.station_name,
                    metrics.factory_name,
                    self._clean_activity(metrics.current_activity),
                    str(metrics.in_queue_size),
                    str(metrics.out_queue_size),
                    str(metrics.workers),
                    f"{metrics.utilization*100:.0f}%",
                    f"{metrics.stress_score*100:.0f}%",
                    "⚠️ YES" if metrics.is_faulted else "✅ No"
                ]
                table.add_row(*row)

    # ------------------------------------------------------------
    # ROW BUILDERS
    # ------------------------------------------------------------
    def _get_overview_row(self, factory):
        """Get row for Overview tab (original format)."""
        q_crushed = f"{factory.q_crushed.size()}/{factory.q_crushed.capacity}"
        q_molded = f"{factory.q_molded.size()}/{factory.q_molded.capacity}"
        q_filled = f"{factory.q_filled.size()}/{factory.q_filled.capacity}" if hasattr(factory, 'q_filled') else "N/A"

        statuses = {}
        for station in factory.stations:
            short_name = station.name.split('-')[-1]
            activity = station.current_activity
            
            status_text = "Idle"
            style = "status-idle"
            
            if "Blocked" in activity:
                status_text = "⛔ Blocked"
                style = "status-blocked"
            elif "Shutdown" in activity:
                status_text = "❌ Down"
                style = "status-blocked"
            elif "Finished" in activity:
                status_text = "✅ Done"
                style = "status-finished"
            elif "Idle" in activity or "Waiting" in activity:
                status_text = "Idle"
                style = "status-idle"
            else:
                status_text = "⚙️ Working"
                style = "status-working"
                
            statuses[short_name] = Text(status_text, style=style)

        return [
            factory.name,
            str(factory.boxer.items_boxed),
            q_crushed,
            q_molded,
            q_filled,
            statuses.get("Crushing", "N/A"),
            statuses.get("Molding", "N/A"),
            statuses.get("Filling", "N/A"),
            statuses.get("Boxing", "N/A"),
        ]

    def _get_factories_row(self, factory):
        """Get row for Factories tab (detailed metrics)."""
        metrics = factory.get_factory_metrics()
        
        q_crushed = f"{factory.q_crushed.size()}/{factory.q_crushed.capacity}"
        q_molded = f"{factory.q_molded.size()}/{factory.q_molded.capacity}"
        q_filled = f"{factory.q_filled.size()}/{factory.q_filled.capacity}" if hasattr(factory, 'q_filled') else "N/A"
        
        # Phase 11: Show total backlog instead of deprecated demand_score
        total_backlog = factory.total_backlog()
        
        return [
            metrics.factory_name,
            str(metrics.total_boxed),
            str(metrics.wip),
            f"{metrics.defect_rate*100:.1f}%",
            f"{metrics.throughput_1m:.1f}",
            str(total_backlog),  # Phase 11: Actual backlog, not legacy demand_score
            q_crushed,
            q_molded,
            q_filled
        ]

    def _clean_activity(self, activity_str: str) -> str:
        """Remove ANSI color codes from activity string."""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', activity_str)

    # ------------------------------------------------------------
    # EVENT HANDLING
    # ------------------------------------------------------------
    def handle_simulation_event(self, event_type: str, data: dict) -> None:
        """Callback for EventBus events."""
        if self._shutdown_requested:
            return
        # Only log important events (not QC or supervisor metrics - too noisy)
        if event_type in ["item_boxed", "station_shutdown", "global_event"]:
            try:
                self.call_from_thread(self.log_event, event_type, data)
            except RuntimeError:
                # App not running anymore, ignore
                pass

    def _pretty_event_type(self, event_type: str, data: dict) -> str:
        """Human-readable event type for the events table."""
        if event_type == "item_boxed" and data.get("golden"):
            return "Golden ticket"
        if event_type == "station_shutdown":
            return "Station shutdown"
        if event_type == "global_event":
            evt = data.get("type")
            mapping = {
                "vip_visit": "VIP visit",
                "robbery": "Robbery",
                "transport_accident": "Transport accident",
                "transport_delay": "Transport delay",
                "demand_spike": "Demand spike",
                "machine_breakdown": "Machine breakdown",
            }
            return mapping.get(evt, f"Global: {evt or 'event'}")
        return event_type

    def _append_event_row(self, event_type: str, data: dict, msg: str) -> None:
        """Append a row to the Events table in the Overview tab."""
        try:
            events_table = self.query_one("#events_table", DataTable)
        except Exception:
            return

        timestamp = time.strftime("%H:%M:%S")
        pretty_type = self._pretty_event_type(event_type, data)

        # Try to show something meaningful in "Factory/City"
        factory = data.get("factory") or data.get("city") or "-"
        station = data.get("station", "-")

        events_table.add_row(
            timestamp,
            pretty_type,
            str(factory),
            str(station),
            msg,
        )

    def log_event(self, event_type: str, data: dict) -> None:
        """Update the Log widget (must run on main thread) and Events table."""
        if self._shutdown_requested:
            return
        log = self.query_one("#overview_log", Log)
        factory_name = data.get("factory", "Unknown")
        
        msg = None
        
        # Filter and Format with consequences
        if event_type == "item_boxed":
            if data.get("golden"):
                msg = f"✨ GOLDEN TICKET found at {factory_name}! Item {data.get('item_id')}"
        elif event_type == "station_shutdown":
            msg = f"❌ {factory_name}: {data.get('station')} has shut down."
        elif event_type == "qc_discard":
            msg = f"🗑️ {factory_name} QC: Discarded item {data.get('item_id')} (temp: {data.get('temperature', 0):.1f}°C)"
        elif event_type == "qc_rework":
            msg = f"🔄 {factory_name} QC: Rework item {data.get('item_id')} (attempt #{data.get('rework_count', 1)})"
        elif event_type == "global_event":
            # Handle global events with actual consequences
            evt = data.get("type")
            if evt == "vip_visit":
                boost = data.get("boost", 1.2)
                msg = f"🌟 VIP Visit at {factory_name}! Demand boost x{boost:.2f}"
            elif evt == "robbery":
                stolen = data.get("stolen_units", 0)
                msg = f"🦹 ROBBERY at {factory_name}! LOST {stolen} boxed chocolates!"
            elif evt == "transport_accident":
                city = data.get("city", "Unknown")
                loss_pct = data.get("loss_percent", 0) * 100
                msg = f"🚛💥 Transport accident to {city}! {loss_pct:.0f}% of shipment lost"
            elif evt == "transport_delay":
                city = data.get("city", "Unknown")
                delay = data.get("delay_factor", 1.0)
                msg = f"🚛⏱️ Transport delays to {city}! Delivery {delay:.1f}x slower"
            elif evt == "demand_spike":
                city = data.get("city", "Unknown")
                mult = data.get("multiplier", 1.0)
                msg = f"📈 Demand spike in {city}! x{mult:.1f} demand"
            elif evt == "machine_breakdown":
                station = data.get("station", "Unknown")
                duration = data.get("duration", 0)
                msg = f"[bold red]🚨 MACHINE BREAKDOWN AT {factory_name.upper()} ({station.upper()})! HALTED FOR {duration}s[/bold red]"
            elif evt == "transport_accident":
                city = data.get("city", "Unknown")
                loss_pct = data.get("loss_percent", 0) * 100
                msg = f"[bold red]🚛💥 TRANSPORT ACCIDENT TO {city.upper()}! {loss_pct:.0f}% OF SHIPMENT LOST[/bold red]"
            elif evt == "transport_delay":
                city = data.get("city", "Unknown")
                delay = data.get("delay_factor", 1.0)
                msg = f"[bold red]🚛⏱️ TRANSPORT DELAY TO {city.upper()}! DELIVERY {delay:.1f}x SLOWER[/bold red]"
            else:
                msg = data.get("msg", "Global event occurred")
        
        if msg:
            # Write to existing log (green panel)
            log.write_line(msg)
            # Also add a row to the Events table
            self._append_event_row(event_type, data, msg)

    # ------------------------------------------------------------
    # ACTIONS
    # ------------------------------------------------------------
    def action_switch_tab(self, tab_id: str) -> None:
        """Switch to a specific tab."""
        if self._shutdown_requested:
            return
        tabbed = self.query_one(TabbedContent)
        tabbed.active = tab_id

    def action_request_shutdown(self) -> None:
        """User pressed q -> graceful shutdown."""
        if self._shutdown_requested:
            return

        self._shutdown_requested = True

        # Show overlay message
        try:
            overlay = self.query_one("#shutdown_overlay", Static)
            overlay.update(
                "🛑 Stopping simulation...\n"
                "Please wait while threads shut down cleanly."
            )
            overlay.display = True
        except Exception:
            pass

        # Run shutdown steps in a background thread
        def shutdown_worker():
            try:
                # Stop supervisor first (if any)
                if self.supervisor and hasattr(self.supervisor, "stop"):
                    self.supervisor.stop()

                # Stop demand engine (if provided)
                if self.demand_engine and hasattr(self.demand_engine, "stop"):
                    self.demand_engine.stop()

                # Stop event engine if we have a ref
                if self.event_engine and hasattr(self.event_engine, "stop"):
                    self.event_engine.stop()

                # Ask simulation to stop factories + stations
                if self.simulation and hasattr(self.simulation, "shutdown_all"):
                    self.simulation.shutdown_all()

                # Optionally stop event bus if it has a stop method
                if self.event_bus and hasattr(self.event_bus, "stop"):
                    self.event_bus.stop()

                # Give threads a tiny moment to finish logs, etc.
                time.sleep(0.5)

            except Exception as e:
                print("Error during graceful shutdown:", e)

            # Close the TUI from the main thread
            self.call_from_thread(self.exit)

        threading.Thread(target=shutdown_worker, daemon=True).start()


def run_textual_dashboard(
    simulation,
    factories,
    event_bus,
    cities=None,
    demand_engine=None,
    supervisor=None,
    event_engine=None,
):
    """Run the Textual TUI dashboard."""
    app = WonkaDashboard(
        simulation,
        factories,
        event_bus,
        cities,
        demand_engine,
        supervisor,
        event_engine,
    )
    app.run()
