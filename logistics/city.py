# logistics/city.py

from typing import Dict
from core.chocolate_type import ChocolateType


class City:
    """City with per-bar-type demand tracking and geographic location."""
    
    def __init__(self, name: str, lat: float, lon: float, demand_strategy=None):
        self.name = name
        self.lat = lat  # Latitude
        self.lon = lon  # Longitude
        self.demand_strategy = demand_strategy
        
        # Phase 11: Per-bar-type demand tracking
        # Base demand: stable baseline demand per bar type
        self.base_demand: Dict[ChocolateType, float] = {
            ChocolateType.CARAMEL: 10.0,
            ChocolateType.HAZELNUT: 10.0,
            ChocolateType.DARK: 10.0,
            ChocolateType.MILK: 10.0,
        }
        
        # Current demand: fluctuating demand (base + noise + events)
        self.current_demand: Dict[ChocolateType, float] = {
            ChocolateType.CARAMEL: 10.0,
            ChocolateType.HAZELNUT: 10.0,
            ChocolateType.DARK: 10.0,
            ChocolateType.MILK: 10.0,
        }
        
        # Order tracking
        self.orders_open: Dict[ChocolateType, int] = {
            ChocolateType.CARAMEL: 0,
            ChocolateType.HAZELNUT: 0,
            ChocolateType.DARK: 0,
            ChocolateType.MILK: 0,
        }
        
        # Shipment tracking
        self.shipments_in_transit: Dict[ChocolateType, int] = {
            ChocolateType.CARAMEL: 0,
            ChocolateType.HAZELNUT: 0,
            ChocolateType.DARK: 0,
            ChocolateType.MILK: 0,
        }
        
        self.shipments_delayed: Dict[ChocolateType, int] = {
            ChocolateType.CARAMEL: 0,
            ChocolateType.HAZELNUT: 0,
            ChocolateType.DARK: 0,
            ChocolateType.MILK: 0,
        }
        
        # Metrics
        self.completed_orders_count = 0
        self.total_fulfillment_time = 0.0  # Sum of (delivered_at - created_at)
        
        #  Legacy inventory (keep for compatibility)
        self.inventory = 0
    
    def request(self):
        """Legacy method for compatibility."""
        if self.demand_strategy:
            return self.demand_strategy.forecast(self)
        return sum(self.current_demand.values())
    
    def total_demand(self) -> float:
        """Total current demand across all bar types."""
        return sum(self.current_demand.values())
    
    def total_orders_open(self) -> int:
        """Total open orders across all bar types."""
        return sum(self.orders_open.values())
    
    def avg_lead_time(self) -> float:
        """Average fulfillment time in seconds."""
        if self.completed_orders_count == 0:
            return 0.0
        return self.total_fulfillment_time / self.completed_orders_count
