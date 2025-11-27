# strategies/qc_strategy.py
"""
QC (Quality Control) Strategy Pattern

Decides whether items pass QC based on temperature and quality metrics.
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from core.item import Item


class QCStrategy(ABC):
    """
    Abstract base for QC decision strategies.
    
    Decides: 'pass', 'rework', or 'discard' based on item conditions.
    """
    
    @abstractmethod
    def inspect(self, item: 'Item') -> Literal['pass', 'rework', 'discard']:
        """
        Inspect an item and make QC decision.
        
        Args:
            item: The item to inspect
            
        Returns:
            'pass' - Item is good, continue to boxing
            'rework' - Send back to molding
            'discard' - Item is too defective, discard it
        """
        pass
    
    @abstractmethod
    def get_strategy_name(self) -> str:
        """Return strategy name for logging."""
        pass


class TemperatureQCStrategy(QCStrategy):
    """
    Temperature-based QC strategy.
    
    Rules:
    - Ideal temperature: 20°C
    - Acceptable range: 10-30°C (pass) - widened tolerance
    - Rework range: 5-35°C (rework) - widened tolerance
    - Outside range: discard
    """
    
    def __init__(
        self,
        ideal_temp: float = 20.0,
        pass_tolerance: float = 10.0,  # ±10°C (was ±5°C)
        rework_tolerance: float = 15.0,  # ±15°C (was ±10°C)
        random_defect_rate: float = 0.01,  # 1% random failures (was 5%)
    ):
        self.ideal_temp = ideal_temp
        self.pass_tolerance = pass_tolerance
        self.rework_tolerance = rework_tolerance
        self.random_defect_rate = random_defect_rate
        
    def inspect(self, item: 'Item') -> Literal['pass', 'rework', 'discard']:
        """Temperature-based inspection."""
        import random
        
        temp = item.temperature
        deviation = abs(temp - self.ideal_temp)
        
        # Random defect chance
        if random.random() < self.random_defect_rate:
            return 'discard'
        
        # Temperature-based decision
        if deviation <= self.pass_tolerance:
            return 'pass'
        elif deviation <= self.rework_tolerance:
            return 'rework'
        else:
            return 'discard'
    
    def get_strategy_name(self) -> str:
        return "TemperatureQC"
