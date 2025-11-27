# strategies/filling_strategy.py

from abc import ABC, abstractmethod
from core.chocolate_type import ChocolateType
from core.item import Item
import random
from typing import TYPE_CHECKING, Dict

if TYPE_CHECKING:
    from core.factory import Factory


class FillingStrategy(ABC):
    """Strategy for choosing chocolate bar type during filling stage."""
    
    @abstractmethod
    def choose_bar_type(self, factory: 'Factory', item: Item) -> ChocolateType:
        """
        Choose the chocolate bar type for this item.
        
        Args:
            factory: Factory reference to access target_mix
            item: Item being filled
            
        Returns:
            ChocolateType to assign to the item
        """
        pass


class WeightedFillingStrategy(FillingStrategy):
    """
    Choose bar type based on factory's target_mix with some randomness.
    
    Uses weighted random selection from target_mix proportions.
    Allows factory to adapt production mix to demand.
    """
    
    def choose_bar_type(self, factory: 'Factory', item: Item) -> ChocolateType:
        """Select bar type using weighted probabilities from factory.target_mix."""
        # Get target mix from factory
        target_mix: Dict[ChocolateType, float] = getattr(factory, 'target_mix', None)
        
        if not target_mix or sum(target_mix.values()) == 0:
            # Fallback to equal distribution if target_mix not set
            return ChocolateType.random_type()
        
        # Weighted random choice
        types = list(target_mix.keys())
        weights = list(target_mix.values())
        
        return random.choices(types, weights=weights, k=1)[0]


class RandomFillingStrategy(FillingStrategy):
    """
    Choose bar type completely randomly, ignoring factory target_mix.
    
    Useful for testing or factories that don't adapt to demand.
    """
    
    def choose_bar_type(self, factory: 'Factory', item: Item) -> ChocolateType:
        """Select bar type randomly."""
        return ChocolateType.random_type()


class BalancedFillingStrategy(FillingStrategy):
    """
    Choose bar type to balance current production throughput.
    
    Favors types with lower throughput_by_type counts.
    Ensures even distribution across bar types.
    """
    
    def choose_bar_type(self, factory: 'Factory', item: Item) -> ChocolateType:
        """Select bar type to balance production."""
        throughput: Dict[ChocolateType, int] = getattr(factory, 'throughput_by_type', None)
        
        if not throughput:
            # Fall back to random if throughput not tracked
            return ChocolateType.random_type()
        
        # Find type with minimum throughput
        min_count = min(throughput.values()) if throughput else 0
        min_types = [t for t, count in throughput.items() if count == min_count]
        
        return random.choice(min_types) if min_types else ChocolateType.random_type()
