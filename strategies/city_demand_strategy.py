# strategies/city_demand_strategy.py

from abc import ABC, abstractmethod
import random
import math
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from logistics.city import City


class CityDemandStrategy(ABC):
    """Strategy for updating city demand over time."""
    
    @abstractmethod
    def update_demand(self, city: 'City', dt: float) -> None:
        """
        Update city's current_demand based on time and market conditions.
        
        Args:
            city: City object to update
            dt: Time delta since last update (seconds)
        """
        pass


class NoisyCityDemandStrategy(CityDemandStrategy):
    """
    Demand fluctuates around base_demand with sinusoidal waves + noise.
    
    Each bar type has independent noise and wave patterns.
    """
    
    def __init__(self, noise_factor: float = 0.2, wave_amplitude: float = 0.3):
        self.noise_factor = noise_factor
        self.wave_amplitude = wave_amplitude
        self._time_offset = random.uniform(0, 100)  # Random phase for waves
    
    def update_demand(self, city: 'City', dt: float) -> None:
        """Update with noise and sinusoidal waves."""
        from core.chocolate_type import ChocolateType
        
        current_time = time.time() + self._time_offset
        
        for bar_type in ChocolateType.all_types():
            base = city.base_demand[bar_type]
            
            # Sinusoidal wave (different frequency per type)
            freq = 0.01 * (1 + list(ChocolateType).index(bar_type) * 0.1)
            wave = math.sin(current_time * freq) * self.wave_amplitude * base
            
            # Random noise
            noise = random.uniform(-self.noise_factor, self.noise_factor) * base
            
            # Update current demand (keep positive)
            city.current_demand[bar_type] = max(0.1, base + wave + noise)


class CaramelLoverStrategy(CityDemandStrategy):
    """City that strongly prefers CARAMEL bars."""
    
    def __init__(self):
        self.preference = {
            'CARAMEL': 2.0,  # 2x base demand
            'HAZELNUT': 0.8,
            'DARK': 0.7,
            'MILK': 0.9,
        }
    
    def update_demand(self, city: 'City', dt: float) -> None:
        """Update with caramel preference."""
        from core.chocolate_type import ChocolateType
        
        for bar_type in ChocolateType.all_types():
            base = city.base_demand[bar_type]
            preference = self.preference.get(bar_type.value, 1.0)
            noise = random.uniform(-0.1, 0.1)
            
            city.current_demand[bar_type] = max(0.1, base * preference * (1 + noise))


class HazelnutFocusedStrategy(CityDemandStrategy):
    """City that strongly prefers HAZELNUT bars."""
    
    def __init__(self):
        self.preference = {
            'CARAMEL': 0.8,
            'HAZELNUT': 2.0,  # 2x base demand
            'DARK': 0.7,
            'MILK': 0.9,
        }
    
    def update_demand(self, city: 'City', dt: float) -> None:
        """Update with hazelnut preference."""
        from core.chocolate_type import ChocolateType
        
        for bar_type in ChocolateType.all_types():
            base = city.base_demand[bar_type]
            preference = self.preference.get(bar_type.value, 1.0)
            noise = random.uniform(-0.1, 0.1)
            
            city.current_demand[bar_type] = max(0.1, base * preference * (1 + noise))


class BalancedDemandStrategy(CityDemandStrategy):
    """City with equal demand for all bar types (minimal fluctuation)."""
    
    def update_demand(self, city: 'City', dt: float) -> None:
        """Update with balanced, stable demand."""
        from core.chocolate_type import ChocolateType
        
        for bar_type in ChocolateType.all_types():
            base = city.base_demand[bar_type]
            small_noise = random.uniform(-0.05, 0.05)
            
            city.current_demand[bar_type] = max(0.1, base * (1 + small_noise))
