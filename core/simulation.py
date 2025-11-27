# core/simulation.py
"""
Phase 7: Multi-Factory Orchestration

Simulation class manages multiple factories, shared EventBus, 
Supervisor, and provides centralized metrics aggregation.
"""

from typing import List, Optional
from observers.event_bus import EventBus
from core.factory import Factory
from core.supervisor import Supervisor
from strategies.supervisor_strategy import SupervisorStrategy
from strategies.aggressive_supervisor import AggressiveSupervisor


class Simulation:
    """
    Orchestrates multi-factory simulation.
    
    Responsibilities:
    - Create and manage multiple factories
    - Wire shared EventBus
    - Coordinate Supervisor
    - Aggregate metrics across all factories
    
    Usage:
        sim = Simulation(event_bus)
        sim.add_factory(factory1)
        sim.add_factory(factory2)
        sim.set_supervisor(AggressiveSupervisor())
        sim.start_all()
    """
    
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.factories: List[Factory] = []
        self.supervisor: Optional[Supervisor] = None
        self._supervisor_strategy: SupervisorStrategy = AggressiveSupervisor()
        
    def add_factory(self, factory: Factory) -> None:
        """Add a factory to the simulation."""
        self.factories.append(factory)
        
    def set_supervisor_strategy(self, strategy: SupervisorStrategy) -> None:
        """Set the supervisor strategy (must be called before start)."""
        self._supervisor_strategy = strategy
        
    def start_all(self) -> None:
        """
        Start all factories and supervisor.
        
        Call this after adding all factories and setting strategy.
        """
        # Create supervisor with all factories
        self.supervisor = Supervisor(
            factories=self.factories,
            event_bus=self.event_bus,
            strategy=self._supervisor_strategy
        )
        
        # Start supervisor
        self.supervisor.start()
        
        # Start all factories
        for factory in self.factories:
            factory.start()
            
    def wait_until_done(self) -> None:
        """Wait for all factories to complete (in parallel, not sequential)."""
        import threading
        
        # Create threads to wait for each factory
        wait_threads = []
        for factory in self.factories:
            t = threading.Thread(target=factory.wait_until_done, daemon=True)
            t.start()
            wait_threads.append(t)
        
        # Wait for all wait threads to complete
        for t in wait_threads:
            t.join()
            
        # Stop supervisor
        if self.supervisor:
            self.supervisor.stop()
            self.supervisor.join(timeout=2.0)
    
    # Phase 11: Demand-driven methods
    def run_for_duration(self, seconds: float) -> None:
        """
        Run simulation for a specific duration (demand-driven mode).
        
        Args:
            seconds: Duration to run in seconds
        """
        import time
        time.sleep(seconds)
    
    def shutdown_all(self) -> None:
        """
        Gracefully shutdown all factories and supervisor (demand-driven mode).
        
        Stops production, cleanup resources, and join threads.
        """
        # Stop all crushing stations (demand-driven)
        for factory in self.factories:
            if hasattr(factory.crusher, 'stop'):
                factory.crusher.stop()
        
        # Stop supervisor
        if self.supervisor:
            self.supervisor.stop()
            self.supervisor.join(timeout=2.0)
        
        # Shutdown queues (to unblock workers)
        for factory in self.factories:
            factory.q_crushed.shutdown()
            factory.q_molded.shutdown()
            if factory.enable_filling:
                factory.q_filled.shutdown()
                factory.q_qc.shutdown()
    
    def get_total_metrics(self) -> dict:
        """Aggregate metrics across all factories."""
        total_cost = sum(f.total_cost for f in self.factories)
        total_revenue = sum(f.total_revenue for f in self.factories)
        total_boxed = sum(f.boxer.items_boxed for f in self.factories)
        
        return {
            "total_factories": len(self.factories),
            "total_cost": total_cost,
            "total_revenue": total_revenue,
            "total_profit": total_revenue - total_cost,
            "total_items_boxed": total_boxed,
            "avg_revenue_per_factory": total_revenue / len(self.factories) if self.factories else 0,
        }
            
    def get_all_factory_metrics(self):
        """Aggregate factory metrics from all factories."""
        return [f.get_factory_metrics() for f in self.factories]
    
    def get_all_station_metrics(self):
        """Aggregate station metrics from all factories."""
        all_metrics = []
        for factory in self.factories:
            all_metrics.extend(factory.get_station_metrics())
        return all_metrics
    
    def get_all_queue_metrics(self):
        """Aggregate queue metrics from all factories."""
        all_metrics = []
        for factory in self.factories:
            all_metrics.extend(factory.get_queue_metrics())
        return all_metrics
    
    def get_total_boxed(self) -> int:
        """Get total items boxed across all factories."""
        return sum(f.boxer.items_boxed for f in self.factories)
    
    def get_average_demand(self) -> float:
        """Get average demand score across all factories."""
        if not self.factories:
            return 1.0
        return sum(f.demand_score for f in self.factories) / len(self.factories)
