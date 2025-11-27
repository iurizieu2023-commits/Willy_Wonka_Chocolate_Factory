# core/demand_model.py
"""
Phase 6: Demand Simulation

Provides pluggable demand models that update factory demand_score 
based on performance, events, and random fluctuations.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.factory import Factory


class DemandModel(ABC):
    """
    Abstract base for demand simulation strategies.
    
    Demand score influences:
    - Supervisor worker scaling decisions
    - Event probabilities (VIP visits)
    - Production priorities
    """
    
    @abstractmethod
    def update_demand(self, factory: 'Factory') -> float:
        """
        Calculate new demand score for the factory.
        
        Args:
            factory: Factory to evaluate
            
        Returns:
            demand_score: float (0.0 - 2.0)
                - 0.0-0.5: Very low demand
                - 0.5-1.0: Low to normal demand
                - 1.0-1.5: Normal to high demand
                - 1.5-2.0: Very high demand
        """
        pass
    
    @abstractmethod
    def get_model_name(self) -> str:
        """Return the model name for logging."""
        pass
