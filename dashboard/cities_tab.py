# dashboard/cities_tab.py

from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.console import RenderableType
from rich.text import Text
from typing import List
from logistics.city import City
import time


def render_delivery_trucks(demand_engine=None) -> RenderableType:
    """
    Render animated delivery trucks showing in-transit orders.
    
    Shows:
    - Truck emoji moving from factory to city
    - Item count and bar type breakdown
    - Progress bar based on ETA
    - Delay warnings
    """
    if not demand_engine:
        return Panel("No delivery data available", title="🚚 Deliveries in Transit", border_style="blue")
    
    # Get in-transit orders
    in_transit = [
        order for order in demand_engine.orders
        if order.status == "IN_TRANSIT"
    ]
    
    if not in_transit:
        return Panel("No active deliveries", title="🚚 Deliveries in Transit", border_style="blue")
    
    # Filter out local deliveries (same city) to show inter-city logistics
    # We want to prioritize displaying long-haul trucks
    inter_city_transit = []
    from utils.geography import haversine_distance
    
    for order in in_transit:
        # Find factory and city to check distance
        # We access factories/cities from demand_engine if available
        is_local = False
        if hasattr(demand_engine, 'factories') and hasattr(demand_engine, 'cities'):
            factory = next((f for f in demand_engine.factories if f.name == order.assigned_factory), None)
            city = next((c for c in demand_engine.cities if c.name == order.city_name), None)
            
            if factory and city:
                dist = haversine_distance(factory.lat, factory.lon, city.lat, city.lon)
                if dist < 50:  # < 50km treated as local/same city
                    is_local = True
        
        if not is_local:
            inter_city_transit.append(order)
    
    # Limit to top 8 deliveries to prevent overflow
    in_transit = inter_city_transit[:8]
    
    # Build delivery lines
    lines = []
    current_time = time.time()
    
    for order in in_transit:
        # Calculate progress (0.0 to 1.0) with safety checks
        elapsed = current_time - order.created_at
        total_time = order.eta - order.created_at
        
        # Safety: prevent division by zero and handle negative values
        if total_time <= 0:
            progress = 1.0  # Treat as complete if ETA in past
        else:
            progress = min(1.0, max(0.0, elapsed / total_time))
        
        # Progress bar (20 chars) with visual enhancements
        bar_length = 20
        filled = int(progress * bar_length)
        
        # Color-code progress bar based on status
        if hasattr(order, '_weather_delayed') and order._weather_delayed:
            bar = "▓" * filled + "░" * (bar_length - filled)  # Standard for delayed
        elif progress > 0.9:
            bar = "█" * filled + "░" * (bar_length - filled)  # Solid blocks for almost done
        else:
            bar = "▓" * filled + "░" * (bar_length - filled)
        
        # Status indicator with ETA
        time_remaining = order.eta - current_time
        if hasattr(order, '_weather_delayed') and order._weather_delayed:
            status = f" ⚠️ +{int(time_remaining)}s"
        elif progress > 0.95:
            status = f" ✓ {int(time_remaining)}s"
        elif time_remaining > 60:
            status = f" ({int(time_remaining/60)}m{int(time_remaining%60):02d}s)"
        else:
            status = f" ({int(time_remaining)}s)"
        
        # Build route string with better spacing
        factory_short = order.assigned_factory.replace("Wonka-", "")
        route = f"🚚 {factory_short:10} → {order.city_name:12}"
        
        # Item count with bar type icon
        bar_icon = {"CARAMEL": "🟧", "HAZELNUT": "🟫", "DARK": "⬛", "MILK": "⬜"}.get(
            order.bar_type.value if order.bar_type else "MILK", "🍫"
        )
        items = f"[{bar_icon}{order.quantity:>2}]"
        
        # Progress percentage
        pct = f"{progress*100:3.0f}%"
        
        # Combine into line
        line = f"{route} {items:7} {bar} {pct}{status}"
        lines.append(line)
    
    # Build content with legend if deliveries exist
    if lines:
        content = "\n".join(lines)
        # Add subtle legend at bottom
        content += "\n" + "─" * 60
        content += "\n▓=progress  ⚠️=delayed  ✓=arriving  ()=ETA"
    else:
        content = "No active deliveries\n\nWaiting for orders to be placed and shipped..."
    
    return Panel(
        content,
        title=f"🚚 Deliveries in Transit ({len(in_transit)} active)",
        border_style="blue",
        padding=(0, 1)
    )


def render_cities_tab(cities: List[City], factories: List = None, demand_engine=None) -> RenderableType:
    """
    Render the Cities & Logistics dashboard tab.
    
    Shows:
    - Table of cities with per-bar-type demand
    - Open orders, shipments in transit/delayed
    - Average lead time
    - Nearest factory and distance
    - Delayed order percentage
    
    Args:
        cities: List of City objects to display
        factories: List of Factory objects for distance calculations
        
    Returns:
        Renderable for Textual dashboard
    """
    from utils.geography import haversine_distance, format_distance
    
    # Create cities table
    table = Table(title="Cities & Logistics", show_header=True, header_style="bold magenta")
    
    # Columns
    table.add_column("City", style="cyan", no_wrap=True, width=10)
    table.add_column("Demand\nIndex", justify="right", style="yellow", width=7)
    table.add_column("🟧\nCar", justify="right", width=5)
    table.add_column("🟫\nHaz", justify="right", width=5)
    table.add_column("⬛\nDrk", justify="right", width=5)
    table.add_column("⬜\nMlk", justify="right", width=5)
    table.add_column("Open\nOrders", justify="right", style="red", width=6)
    table.add_column("Transit", justify="right", style="blue", width=7)
    table.add_column("Delayed", justify="right", style="magenta", width=7)
    table.add_column("Nearest\nFactory", justify="left", style="green", width=12)
    table.add_column("Dist", justify="right", style="green", width=6)
    table.add_column("Avg\nLead(s)", justify="right", style="cyan", width=7)
    
    # Add rows for each city
    for city in cities:
        from core.chocolate_type import ChocolateType
        
        # Calculate demand index (sum of all bar types)
        demand_idx = city.total_demand()
        
        # Get per-bar-type demand (rounded)
        caramel_demand = f"{city.current_demand.get(ChocolateType.CARAMEL, 0):.0f}"
        hazelnut_demand = f"{city.current_demand.get(ChocolateType.HAZELNUT, 0):.0f}"
        dark_demand = f"{city.current_demand.get(ChocolateType.DARK, 0):.0f}"
        milk_demand = f"{city.current_demand.get(ChocolateType.MILK, 0):.0f}"
        
        # Get order and shipment stats
        open_orders = city.total_orders_open()
        in_transit = sum(city.shipments_in_transit.values())
        delayed = sum(city.shipments_delayed.values())
        avg_lead = city.avg_lead_time()
        
        # Find nearest factory
        nearest_factory_name = "-"
        nearest_distance = 0
        if factories:
            nearest_factory = min(factories, key=lambda f: haversine_distance(f.lat, f.lon, city.lat, city.lon))
            nearest_distance = haversine_distance(nearest_factory.lat, nearest_factory.lon, city.lat, city.lon)
            # Shorten factory name (remove "Wonka-" prefix)
            nearest_factory_name = nearest_factory.name.replace("Wonka-", "")
        
        # Format distance
        dist_str = format_distance(nearest_distance) if factories else "-"
        
        # Format avg lead time - show "-" if no completed orders
        if city.completed_orders_count > 0:
            avg_lead_str = f"{avg_lead:.1f}"
        else:
            avg_lead_str = "-"
        
        table.add_row(
            city.name,
            f"{demand_idx:.0f}",
            caramel_demand,
            hazelnut_demand,
            dark_demand,
            milk_demand,
            str(open_orders),
            str(in_transit),
            str(delayed),
            nearest_factory_name,
            dist_str,
            avg_lead_str,
        )
    
    # Logistics summary
    total_orders = sum(c.total_orders_open() for c in cities)
    total_transit = sum(sum(c.shipments_in_transit.values()) for c in cities)
    total_delayed = sum(sum(c.shipments_delayed.values()) for c in cities)
    total_completed = sum(c.completed_orders_count for c in cities)
    
    # Calculate global delayed %
    delayed_pct = (total_delayed / (total_completed + total_delayed) * 100) if (total_completed + total_delayed) > 0 else 0
    
    summary = (f"📊 Total: {total_orders} orders open | {total_transit} in transit | "
               f"{total_delayed} delayed ({delayed_pct:.1f}%) | {total_completed} delivered")
    
    # Create layout with three sections
    layout = Layout()
    layout.split_column(
        Layout(table, name="table", size=len(cities) + 4),
        Layout(Panel(summary, title="Logistics Summary", border_style="blue"), name="summary", size=3),
        Layout(render_delivery_trucks(demand_engine), name="deliveries", size=12),
    )
    
    return layout
