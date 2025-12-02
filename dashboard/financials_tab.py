# dashboard/financials_tab.py

from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.console import RenderableType
from rich.text import Text
from typing import List
import time


def render_financials_tab(factories: List) -> RenderableType:
    """
    Render the Financials dashboard tab.
    
    Shows:
    - Factory-level financial metrics
    - Global financial summary
    - Cost breakdown by category
    """
    
    # Factory-level financials table
    factory_table = Table(title="Factory Financial Performance", show_header=True, header_style="bold cyan")
    factory_table.add_column("Factory", style="cyan", no_wrap=True)
    factory_table.add_column("Revenue", justify="right", style="green")
    factory_table.add_column("Costs", justify="right", style="yellow")
    factory_table.add_column("Profit", justify="right")
    factory_table.add_column("Margin", justify="right")
    factory_table.add_column("Items", justify="right")
    factory_table.add_column("Cost/Item", justify="right")
    
    total_revenue = 0.0
    total_cost = 0.0
    total_items = 0
    total_breakdown_costs = 0.0
    total_transport_losses = 0.0
    
    for factory in factories:
        revenue = factory.total_revenue
        cost = factory.total_cost
        profit = revenue - cost
        items = factory.boxer.items_boxed
        
        # Calculate margin
        margin = (profit / revenue * 100) if revenue > 0 else 0.0
        
        # Cost per item
        cost_per_item = cost / items if items > 0 else 0.0
        
        # Style profit based on positive/negative
        if profit >= 0:
            profit_str = f"${profit:,.0f}"
            profit_style = "green"
        else:
            profit_str = f"-${abs(profit):,.0f}"
            profit_style = "red"
        
        # Check for active cocoa shortage
        status = ""
        if time.time() < factory.cocoa_shortage_until:
            status = " ⚠️"
            profit_style = "red bold"
        
        # Check for VIP shield
        if time.time() < factory.vip_shield_until:
            status += " 🛡️"
        
        factory_table.add_row(
            factory.name.replace("Wonka-", "") + status,
            f"${revenue:,.0f}",
            f"${cost:,.0f}",
            Text(profit_str, style=profit_style),
            f"{margin:.1f}%",
            str(items),
            f"${cost_per_item:.2f}"
        )
        
        total_revenue += revenue
        total_cost += cost
        total_items += items
        total_breakdown_costs += factory.breakdown_costs
        total_transport_losses += factory.transport_losses
        
    # Global summary
    total_profit = total_revenue - total_cost
    global_margin = (total_profit / total_revenue * 100) if total_revenue > 0 else 0.0
    avg_cost_per_item = total_cost / total_items if total_items > 0 else 0.0
    
    # Production costs (subtract special costs)
    production_costs = total_cost - total_breakdown_costs - total_transport_losses
    
    summary_lines = [
        f"Total Revenue:     ${total_revenue:,.0f}",
        f"Total Costs:       ${total_cost:,.0f}",
        f"Net Profit:        ${total_profit:,.0f}",
        f"Profit Margin:     {global_margin:.1f}%",
        "",
        f"Items Produced:    {total_items:,}",
        f"Avg Cost/Item:     ${avg_cost_per_item:.2f}",
    ]
    
    summary_panel = Panel(
        "\n".join(summary_lines),
        title="Global Financial Summary",
        border_style="green" if total_profit >= 0 else "red"
    )
    
    # Cost breakdown
    if total_cost > 0:
        prod_pct = (production_costs / total_cost * 100)
        break_pct = (total_breakdown_costs / total_cost * 100)
        trans_pct = (total_transport_losses / total_cost * 100)
    else:
        prod_pct = break_pct = trans_pct = 0.0
    


    breakdown_lines = [
        f"Production:        ${production_costs:,.0f}  ({prod_pct:.1f}%)",
        f"Breakdowns:        ${total_breakdown_costs:,.0f}  ({break_pct:.1f}%)",
        f"Transport Loss:    ${total_transport_losses:,.0f}  ({trans_pct:.1f}%)",
    ]
    
    breakdown_panel = Panel(
        "\n".join(breakdown_lines),
        title="Cost Breakdown",
        border_style="yellow"
    )
    
    # Create layout
    layout = Layout()
    layout.split_column(
        Layout(factory_table, name="factory_table", size=len(factories) + 4),
        Layout(summary_panel, name="summary", size=10),
        Layout(breakdown_panel, name="breakdown", size=6),
    )
    
    return layout
