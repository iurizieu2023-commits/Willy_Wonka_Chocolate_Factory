# strategies/aggressive_supervisor.py
from strategies.supervisor_strategy import SupervisorStrategy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.factory import Factory
    from core.station import ScalableStation
    from core.item import Item


class AggressiveSupervisor(SupervisorStrategy):
    """
    Aggressive supervisor strategy:
    - Quick to scale up workers when queues grow
    - Low stress tolerance (repair early)
    - Strict quality control (discard defects)
    """
    
    def __init__(
        self,
        queue_threshold_high: float = 0.6,  # Queue >60% triggers scale up
        queue_threshold_low: float = 0.2,   # Queue <20% triggers scale down
        stress_repair_threshold: float = 0.6,  # Repair at 60% stress
        quality_threshold: float = 0.7,     # Quality <70% gets discarded
    ):
        self.queue_threshold_high = queue_threshold_high
        self.queue_threshold_low = queue_threshold_low
        self.stress_repair_threshold = stress_repair_threshold
        self.quality_threshold = quality_threshold
        
    def decide_scaling(self, factory: 'Factory', station: 'ScalableStation') -> int:
        """Aggressive scaling: react quickly to queue pressure."""
        # Get queue utilization
        queue_size = station.in_queue.size()
        queue_capacity = station.in_queue.capacity
        utilization = queue_size / queue_capacity if queue_capacity > 0 else 0
        
        # Get current worker count
        worker_count = len(station.workers)
        
        # Demand multiplier (if factory has demand_score)
        demand_multiplier = getattr(factory, 'demand_score', 1.0)
        
        # Scale up aggressively
        if utilization > self.queue_threshold_high and worker_count < 5:
            # Cap at 5 workers per station
            return 1
        
        # Scale down if idle and demand is low
        elif utilization < self.queue_threshold_low and worker_count > 1 and demand_multiplier < 0.8:
            return -1
        
        return 0
    
    def should_repair(self, station: 'ScalableStation') -> bool:
        """Repair early at low stress threshold."""
        return station.is_faulted or station.stress_score > self.stress_repair_threshold
    
    def qc_decision(self, item: 'Item') -> str:
        """Strict QC: discard low quality items."""
        if item.quality_score < self.quality_threshold:
            return 'discard'
        elif item.quality_score < 0.85:
            return 'rework'
        else:
            return 'pass'
    
    def get_strategy_name(self) -> str:
        return "AggressiveSupervisor"
