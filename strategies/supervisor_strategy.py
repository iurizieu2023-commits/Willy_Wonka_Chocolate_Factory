# strategies/supervisor_strategy.py
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.factory import Factory
    from core.station import ScalableStation
    from core.item import Item


class SupervisorStrategy(ABC):
    """
    Strategy pattern for supervisor decisions.
    
    Responsibilities:
    - Worker scaling decisions (add/remove workers)
    - Fault detection and repair triggers
    - Quality control rules
    """
    
    @abstractmethod
    def decide_scaling(self, factory: 'Factory', station: 'ScalableStation') -> int:
        """
        Decide whether to scale workers at this station.
        
        Args:
            factory: The factory context (for demand_score, metrics, etc.)
            station: The station to evaluate
            
        Returns:
            delta: +1 to add worker, -1 to remove worker, 0 for no change
        """
        pass
    
    @abstractmethod
    def should_repair(self, station: 'ScalableStation') -> bool:
        """
        Check if a station needs repair.
        
        Args:
            station: The station to evaluate
            
        Returns:
            True if repair should be triggered
        """
        pass
    
    @abstractmethod
    def qc_decision(self, item: 'Item') -> str:
        """
        Quality control decision for an item.
        
        Args:
            item: The item to evaluate
            
        Returns:
            'pass' | 'rework' | 'discard'
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return the strategy name for logging."""
        pass
