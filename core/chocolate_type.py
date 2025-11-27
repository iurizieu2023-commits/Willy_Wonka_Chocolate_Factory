# core/chocolate_type.py

from enum import Enum
from typing import List
import random


class ChocolateType(Enum):
    """Chocolate bar types for production and demand tracking."""
    CARAMEL = "CARAMEL"
    HAZELNUT = "HAZELNUT"
    DARK = "DARK"
    MILK = "MILK"
    
    def __str__(self):
        return self.value
    
    @classmethod
    def all_types(cls) -> List['ChocolateType']:
        """Return all chocolate types as a list."""
        return list(cls)
    
    @classmethod
    def random_type(cls) -> 'ChocolateType':
        """Return a random chocolate type."""
        return random.choice(list(cls))
    
    def color_code(self) -> str:
        """Return color code for dashboard display."""
        colors = {
            ChocolateType.CARAMEL: "\033[38;5;214m",  # Orange
            ChocolateType.HAZELNUT: "\033[38;5;130m",  # Brown
            ChocolateType.DARK: "\033[38;5;236m",      # Dark gray
            ChocolateType.MILK: "\033[38;5;231m",      # Light/white
        }
        return colors.get(self, "")
    
    def icon(self) -> str:
        """Return emoji icon for this bar type."""
        icons = {
            ChocolateType.CARAMEL: "🟧",
            ChocolateType.HAZELNUT: "🟫",
            ChocolateType.DARK: "⬛",
            ChocolateType.MILK: "⬜",
        }
        return icons.get(self, "🍫")
