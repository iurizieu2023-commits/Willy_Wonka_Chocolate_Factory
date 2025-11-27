# core/supervisor.py
import threading
import time
from typing import Dict, List, TYPE_CHECKING

from core.queue import BoundedQueue
from core.item import Item
from observers.event_bus import EventBus
from strategies.supervisor_strategy import SupervisorStrategy

if TYPE_CHECKING:
    from core.factory import Factory
    from core.station import ScalableStation


class Supervisor(threading.Thread):
    """
    Phase 3: Upgraded Supervisor with Strategy pattern.
    
    Responsibilities:
    - Monitor all stations across all factories
    - Apply strategy decisions:
      * Worker scaling (add/remove)
      * Fault detection and repair
      * Quality control
    
    Usage:
        from strategies.aggressive_supervisor import AggressiveSupervisor
        supervisor = Supervisor(
            factories=[factory1, factory2],
            event_bus=event_bus,
            strategy=AggressiveSupervisor()
        )
        supervisor.start()
    """

    def __init__(
        self,
        factories: List['Factory'],
        event_bus: EventBus,
        strategy: SupervisorStrategy,
        poll_interval: float = 2.0,
        db_manager=None  # Phase 13: Database logging
    ) -> None:
        super().__init__(name="Supervisor", daemon=True)
        self.factories = factories
        self.event_bus = event_bus
        self.strategy = strategy
        self.poll_interval = poll_interval
        self.db_manager = db_manager  # Store for logging
        self._running = True
        
        # Subscribe to fault events
        self.event_bus.subscribe("station_fault", self._on_station_fault)

    def stop(self) -> None:
        self._running = False

    def run(self) -> None:
        """Main supervisor loop: monitor, decide, act."""
        while self._running:
            time.sleep(self.poll_interval)
            
            for factory in self.factories:
                self._monitor_factory(factory)

    def _monitor_factory(self, factory: 'Factory') -> None:
        """
        Monitor one factory and make scaling decisions.
        
        Phase 3: Uses SupervisorStrategy to decide scaling actions.
        Phase 11: Also monitors backlog and adjusts target_mix.
        """
        # Get factory metrics
        metrics = factory.get_factory_metrics()
        station_metrics = factory.get_station_metrics()
        queue_metrics = factory.get_queue_metrics()
        
        # Use strategy to make decisions
        actions = self.strategy.decide_scaling(
            factory=factory,
            factory_metrics=metrics,
            station_metrics=station_metrics,
            queue_metrics=queue_metrics
        )
        
        # Execute scaling actions
        for action in actions:
            station_name = action.get('station')
            change = action.get('change')  # +1 or -1
            
            # Find station
            station = None
            for s in factory.stations:
                if s.name == station_name:
                    station = s
                    break
            
            if station and hasattr(station, 'add_worker'):
                if change > 0:
                    station.add_worker()
                    self.scaling_actions_count += 1
                    
                    # Phase 13: Log supervisor action
                    if self.db_manager:
                        reason = action.get('reason', f'Scaling up {station_name}')
                        self.db_manager.log_supervisor_action(
                            factory=factory,
                            station=station,
                            action_type='worker_add',
                            delta_workers=1,
                            reason=reason
                        )
                        
                elif change < 0 and hasattr(station, 'remove_worker'):
                    station.remove_worker()
                    self.scaling_actions_count += 1
                    
                    # Phase 13: Log supervisor action
                    if self.db_manager:
                        reason = action.get('reason', f'Scaling down {station_name}')
                        self.db_manager.log_supervisor_action(
                            factory=factory,
                            station=station,
                            action_type='worker_remove',
                            delta_workers=-1,
                            reason=reason
                        )
        
        # Phase 11: Monitor backlog and adjust target_mix
        if hasattr(factory, 'backlog_by_type') and hasattr(factory, 'target_mix'):
            from core.chocolate_type import ChocolateType
            
            # Calculate backlog ratio per bar type
            total_backlog = factory.total_backlog()
            if total_backlog > 0:
                # Adjust target_mix to favor bar types with higher backlog
                new_mix = {}
                for bar_type in ChocolateType.all_types():
                    backlog = factory.backlog_by_type.get(bar_type, 0)
                    # Weight: 50% current mix + 50% backlog proportion
                    current_weight = factory.target_mix.get(bar_type, 0.25)
                    backlog_proportion = backlog / total_backlog if total_backlog > 0 else 0.25
                    new_mix[bar_type] = 0.5 * current_weight + 0.5 * backlog_proportion
                
                # Normalize and update
                factory.update_target_mix(new_mix)

    def repair_station(self, station: 'ScalableStation') -> None:
        """
        Repair a faulted station:
        - Clear fault flag
        - Reset stress score
        - Publish repair event
        """
        station.repair()
        # Event is already published by station.repair()
        
    def _on_station_fault(self, event_type: str, data: dict) -> None:
        """React to fault events immediately (callback)."""
        # This could trigger immediate repair or escalation
        # For now, we let the main loop handle it
        pass
