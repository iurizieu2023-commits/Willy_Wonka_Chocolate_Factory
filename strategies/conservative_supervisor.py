# strategies/conservative_supervisor.py
from strategies.supervisor_strategy import SupervisorStrategy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.factory import Factory
    from core.station import ScalableStation
    from core.item import Item


class ConservativeSupervisor(SupervisorStrategy):
    """
    Conservative supervisor strategy:
    - Slow to scale (minimize worker changes)
    - High stress tolerance (let stations run hot)
    - Lenient quality control (allow rework)
    """
    
    def __init__(
        self,
        queue_threshold_high: float = 0.85,  # Queue >85% triggers scale up
        queue_threshold_low: float = 0.1,    # Queue <10% triggers scale down
        stress_repair_threshold: float = 0.85,  # Repair only at 85% stress
        quality_threshold: float = 0.5,      # Quality <50% gets discarded
    ):
        self.queue_threshold_high = queue_threshold_high
        self.queue_threshold_low = queue_threshold_low
        self.stress_repair_threshold = stress_repair_threshold
        self.quality_threshold = quality_threshold
        
    def decide_scaling(self, factory: 'Factory', station: 'ScalableStation') -> int:
        """Conservative scaling: minimize changes, only act on extremes."""
        # Get queue utilization
        queue_size = station.in_queue.size()
        queue_capacity = station.in_queue.capacity
        utilization = queue_size / queue_capacity if queue_capacity > 0 else 0
        
        # Get current worker count
        worker_count = len(station.workers)
        
        # Demand multiplier
        demand_multiplier = getattr(factory, 'demand_score', 1.0)
        
        # Scale up only when critically full
        if utilization > self.queue_threshold_high and worker_count < 3:
            # Cap at 3 workers (conservative)
            return 1
        
        # Scale down only when nearly empty and low demand
        elif utilization < self.queue_threshold_low and worker_count > 1 and demand_multiplier < 0.5:
            return -1
        
        return 0
    
    def should_repair(self, station: 'ScalableStation') -> bool:
        """Repair only when critically stressed."""
        return station.is_faulted and station.stress_score > self.stress_repair_threshold
    
    def qc_decision(self, item: 'Item') -> str:
        """Lenient QC: prefer rework over discard."""
        if item.quality_score < self.quality_threshold:
            return 'discard'
        elif item.quality_score < 0.9:
            return 'rework'
        else:
            return 'pass'
    
    def get_strategy_name(self) -> str:
        return "ConservativeSupervisor"
