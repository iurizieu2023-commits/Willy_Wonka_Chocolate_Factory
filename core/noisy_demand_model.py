# core/noisy_demand_model.py
"""
Phase 6: NoisyDemandModel implementation.

Demand fluctuates based on:
- Random noise (market volatility)
- Recent performance (throughput, delays)
- Recent events (robbery reduces demand, VIP increases)
"""

import random
from core.demand_model import DemandModel
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.factory import Factory


class NoisyDemandModel(DemandModel):
    """
    Noisy demand model: random walk + performance influence.
    
    Features:
    - Random walk with drift
    - Increases with good performance (high throughput, low defects)
    - Decreases with bad events (robberies, breakdowns)
    - Mean-reverting (tends toward 1.0)
    """
    
    def __init__(
        self,
        volatility: float = 0.1,  # Random noise magnitude
        mean_reversion: float = 0.05,  # Pull toward 1.0
        performance_weight: float = 0.02,  # Performance influence
    ):
        self.volatility = volatility
        self.mean_reversion = mean_reversion
        self.performance_weight = performance_weight
        
        # Track event history for demand adjustment
        self._recent_events = []
        self._max_event_history = 5
        
    def update_demand(self, factory: 'Factory') -> float:
        """
        Update demand score using random walk + performance.
        """
        current_demand = factory.demand_score
        
        # 1. Random noise (market volatility)
        noise = random.uniform(-self.volatility, self.volatility)
        
        # 2. Mean reversion (pull toward 1.0)
        reversion = -self.mean_reversion * (current_demand - 1.0)
        
        # 3. Performance influence
        metrics = factory.get_factory_metrics()
        
        # Positive factors: throughput, low defects
        performance_factor = 0.0
        if metrics.uptime > 0:
            # High throughput → increased demand
            performance_factor += metrics.throughput_1m * 0.001
            
            # Low defect rate → increased demand
            performance_factor -= metrics.defect_rate * 0.1
        
        performance_delta = self.performance_weight * performance_factor
        
        # 4. Event influence (future: subscribe to EventBus)
        # For now, events are handled externally
        
        # Combine all factors
        new_demand = current_demand + noise + reversion + performance_delta
        
        # Clamp to valid range [0.0, 2.0]
        new_demand = max(0.0, min(2.0, new_demand))
        
        return new_demand
    
    def get_model_name(self) -> str:
        return "NoisyDemandModel"
