# strategies/routing_strategy.py

from abc import ABC, abstractmethod
from typing import List, TYPE_CHECKING
import random

if TYPE_CHECKING:
    from logistics.order import Order
    from core.factory import Factory


class RoutingStrategy(ABC):
    """Strategy for assigning orders to factories."""
    
    @abstractmethod
    def assign_factory(self, order: 'Order', factories: List['Factory'], city_lat: float, city_lon: float) -> 'Factory':
        """
        Assign an order to the most suitable factory.
        
        Args:
            order: Order to assign
            factories: List of available factories
            city_lat, city_lon: Order destination coordinates
            
        Returns:
            Selected factory
        """
        pass


class ProximityRoutingStrategy(RoutingStrategy):
    """Assign to nearest factory with available capacity."""
    
    def __init__(self, max_backlog_threshold: int = 200):
        self.max_backlog_threshold = max_backlog_threshold
    
    def assign_factory(self, order: 'Order', factories: List['Factory'], city_lat: float, city_lon: float) -> 'Factory':
        """Assign to nearest factory that isn't overloaded."""
        from utils.geography import haversine_distance
        
        if not factories:
            return None
        
        # Filter factories with capacity
        available = [f for f in factories if f.total_backlog() < self.max_backlog_threshold]
        
        if not available:
            # All overloaded, pick least loaded
            available = sorted(factories, key=lambda f: f.total_backlog())[:len(factories)//2 + 1]
        
        # Find nearest
        best_factory = None
        min_distance = float('inf')
        
        for factory in available:
            distance = haversine_distance(factory.lat, factory.lon, city_lat, city_lon)
            if distance < min_distance:
                min_distance = distance
                best_factory = factory
        
        return best_factory or factories[0]


class BalancedRoutingStrategy(RoutingStrategy):
    """Balance between proximity and workload."""
    
    def __init__(self, proximity_weight: float = 0.6, workload_weight: float = 0.4):
        self.proximity_weight = proximity_weight
        self.workload_weight = workload_weight
    
    def assign_factory(self, order: 'Order', factories: List['Factory'], city_lat: float, city_lon: float) -> 'Factory':
        """Score factories: 60% proximity + 40% low workload."""
        from utils.geography import haversine_distance
        
        if not factories:
            return None
        
        scores = []
        for factory in factories:
            distance = haversine_distance(factory.lat, factory.lon, city_lat, city_lon)
            backlog = factory.total_backlog()
            
            # Normalize (inverse for both - lower is better)
            # Proximity score: 1 / (distance + 1) to avoid division by zero
            proximity_score = 1.0 / (distance + 1.0)
            
            # Workload score: 1 / (backlog + 1)
            workload_score = 1.0 / (backlog + 1.0)
            
            # Weighted combination
            total_score = (self.proximity_weight * proximity_score + 
                          self.workload_weight * workload_score)
            
            scores.append((total_score, factory))
        
        # Return highest scoring factory
        scores.sort(reverse=True, key=lambda x: x[0])
        return scores[0][1]


class RoundRobinRoutingStrategy(RoutingStrategy):
    """Simple round-robin assignment (legacy)."""
    
    def __init__(self):
        self.index = 0
    
    def assign_factory(self, order: 'Order', factories: List['Factory'], city_lat: float, city_lon: float) -> 'Factory':
        """Cycle through factories."""
        if not factories:
            return None
        
        factory = factories[self.index % len(factories)]
        self.index += 1
        return factory


class RegionalRoutingStrategy(RoutingStrategy):
    """
    Route to factories in the same geographic region first.
    
    Prevents unrealistic cross-ocean routing (e.g., Sydney → São Paulo).
    Falls back to global routing if no regional factories available.
    """
    
    REGIONS = {
        'Europe': {
            'cities': ['London', 'Paris'],
            'factories': ['Wonka-London', 'Wonka-Paris'],
        },
        'Americas': {
            'cities': ['New York', 'São Paulo'],
            'factories': ['Wonka-NewYork', 'Wonka-Brazil'],
        },
        'Asia-Pacific': {
            'cities': ['Tokyo', 'Sydney'],
            'factories': ['Wonka-Tokyo'],
        },
    }
    
    def __init__(self, fallback_strategy=None):
        """
        Args:
            fallback_strategy: Strategy to use if no regional factories available
        """
        self.fallback_strategy = fallback_strategy or BalancedRoutingStrategy()
    
    def _find_city_region(self, city_name: str) -> str:
        """Find which region a city belongs to."""
        for region, data in self.REGIONS.items():
            if any(city in city_name for city in data['cities']):
                return region
        return None
    
    def _filter_regional_factories(self, factories: List['Factory'], region: str) -> List['Factory']:
        """Filter factories that belong to the given region."""
        if region is None:
            return factories
        
        region_data = self.REGIONS.get(region, {})
        region_factory_names = region_data.get('factories', [])
        
        return [f for f in factories if any(name in f.name for name in region_factory_names)]
    
    def assign_factory(self, order: 'Order', factories: List['Factory'], city_lat: float, city_lon: float) -> 'Factory':
        """Assign to regional factory first, fall back to global if needed."""
        from utils.geography import haversine_distance
        
        if not factories:
            return None
        
        # Find city region
        region = self._find_city_region(order.city_name)
        
        # Filter to regional factories
        regional_factories = self._filter_regional_factories(factories, region)
        
        if regional_factories:
            # Use fallback strategy on regional subset
            return self.fallback_strategy.assign_factory(order, regional_factories, city_lat, city_lon)
        else:
            # No regional factories, use global
            return self.fallback_strategy.assign_factory(order, factories, city_lat, city_lon)
