# logistics/order.py

from dataclasses import dataclass
from typing import Optional
import time
from core.chocolate_type import ChocolateType


@dataclass
class Order:
    """Represents an order from a city for a specific chocolate bar type."""
    
    city_name: str  # Name of the city placing the order
    bar_type: ChocolateType  # Type of chocolate bar ordered
    quantity: int  # Number of items ordered
    created_at: float# Timestamp when order was created
    eta: float  # Estimated delivery time (timestamp)
    assigned_factory: Optional[str] = None  # Factory assigned to fulfill this order
    status: str = "PENDING"  # PENDING, IN_TRANSIT, DELAYED, DELIVERED, CANCELLED
    
    def __post_init__(self):
        """Initialize created_at to current time if not provided."""
        if self.created_at == 0:
            self.created_at = time.time()
        if self.eta == 0:
            self.eta = self.created_at + 30.0  # Default 30s ETA
    
    def lead_time(self) -> float:
        """Calculate lead time from creation to delivery (or current time if not delivered)."""
        if self.status == "DELIVERED":
            return self.eta - self.created_at  # Actual delivery time
        else:
            return time.time() - self.created_at  # Time so far
    
    def is_overdue(self) -> bool:
        """Check if order is overdue based on ETA."""
        return time.time() > self.eta and self.status not in ["DELIVERED", "CANCELLED"]
