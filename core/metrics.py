# core/metrics.py
"""
Phase 4: Metrics API for dashboard and monitoring.

Provides clean dataclasses for:
- Factory-level metrics (throughput, defect rate, WIP)
- Station-level metrics (utilization, workers, latency)
- Queue-level metrics (size, capacity, blocked status)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class FactoryMetrics:
    """Factory-level metrics snapshot."""
    factory_name: str
    total_boxed: int
    wip: int  # Work in progress
    defect_count: int
    defect_rate: float  # 0.0 - 1.0
    throughput_1m: float  # Items per minute
    uptime: float  # Seconds since start
    demand_score: float  # Current demand (0.0 - 2.0)
    # Financial metrics
    total_cost: float  # Total production cost
    total_revenue: float  # Total revenue from boxed items
    profit: float  # revenue - cost


@dataclass
class StationMetrics:
    """Station-level metrics snapshot."""
    station_name: str
    factory_name: str
    current_activity: str
    utilization: float  # 0.0 - 1.0
    is_faulted: bool
    stress_score: float  # 0.0 - 1.0
    avg_latency_ms: float
    workers: int
    in_queue_size: int
    out_queue_size: int
    last_processed_item_id: Optional[int]
    items_processed: int


@dataclass
class QueueMetrics:
    """Queue-level metrics snapshot."""
    name: str
    size: int
    max_size: int
    utilization: float  # size / max_size
    blocked: bool  # True if producers are blocked
    
    @property
    def is_full(self) -> bool:
        return self.size >= self.max_size
    
    @property
    def is_nearly_full(self) -> bool:
        return self.utilization > 0.8
