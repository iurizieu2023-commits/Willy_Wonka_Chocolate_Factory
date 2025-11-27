# events/event_engine.py

import threading
import time
import random
from typing import List, TYPE_CHECKING
from observers.event_bus import EventBus
import global_state

if TYPE_CHECKING:
    from core.factory import Factory


class EventEngine(threading.Thread):
    """
    Phase 5: Probabilistic event engine.
    
    Produces random global events with probabilities based on factory metrics:
    - Robbery: probability ∝ golden tickets boxed
    - VIP visit: probability ∝ factory efficiency (throughput / defect_rate)
    - Logistics: transport delays and accidents
    
    Publishes to EventBus for Dashboard and Supervisors to react.
    """

    def __init__(
        self, 
        event_bus: EventBus, 
        factories: List['Factory'] = None,
        period: float = 8.0
    ) -> None:
        super().__init__(name="EventEngine", daemon=True)
        self.event_bus = event_bus
        self.factories = factories or []
        self.period = period
        self._running = True
        
        # Phase 5: Track golden ticket count per factory for robbery probability
        self._golden_count = {}

    def stop(self) -> None:
        self._running = False
        
    def set_factories(self, factories: List['Factory']) -> None:
        """Set factories to monitor (can be called after __init__)."""
        self.factories = factories

    # -------------------------------------------------------
    # Phase 5: Probabilistic event generators
    # -------------------------------------------------------

    def _calculate_robbery_probability(self, factory: 'Factory') -> float:
        """
        Probability based on GOLDEN TICKETS in production (WIP).
        Scales exponentially to create high risk with many golden tickets.
        """
        # Count golden tickets currently in queues
        wip_golden = factory.get_wip_golden_tickets()
        
        if wip_golden == 0:
            return 0.02  # 2% base probability with no golden tickets
        elif wip_golden == 1:
            return 0.10  # 10% with 1 golden ticket
        elif wip_golden == 2:
            return 0.25  # 25% with 2 golden tickets
        elif wip_golden == 3:
            return 0.45  # 45% with 3 golden tickets
        elif wip_golden >= 4:
            return 0.70  # 70% with 4+ golden tickets - very high risk!
        
        # Exponential scaling formula as backup
        # P(robbery) = min(0.70, 0.02 + (wip_golden^2 * 0.08))
        return min(0.70, 0.02 + (wip_golden ** 2) * 0.08)
    
    def _calculate_vip_probability(self, factory: 'Factory') -> float:
        """VIP visit probability scales with factory efficiency."""
        metrics = factory.get_factory_metrics()
        
        # Efficiency = throughput / (1 + defect_rate)
        # Higher throughput, lower defects → higher VIP chance
        efficiency = metrics.throughput_1m / (1 + metrics.defect_rate)
        
        # Base probability: 0.1 (10%)
        # +0.005 per item/min throughput, capped at 0.4 (40%)
        prob = min(0.1 + efficiency * 0.005, 0.4)
        return prob

    def _robbery(self):
        """
        Phase 13: Robbery respects VIP shield.
        Targets factory with most golden tickets, but skips protected factories.
        Probability scales with golden tickets but reduced by recent security improvements.
        """
        if not self.factories:
            return None
        
        # Filter out VIP-shielded factories
        eligible_factories = [
            f for f in self.factories
            if time.time() > f.vip_shield_until and f.get_wip_golden_tickets() > 0
        ]
        
        if not eligible_factories:
            return None  # All factories either protected or have no golden tickets
        
        # Sort by golden ticket count (descending)
        eligible_factories.sort(key=lambda f: f.get_wip_golden_tickets(), reverse=True)
        factory = eligible_factories[0]
        wip_golden = factory.get_wip_golden_tickets()
        
        # Calculate base robbery probability from golden tickets
        base_prob = self._calculate_robbery_probability(factory)
        
        # Apply security cooldown - reduces probability if recently robbed
        import time
        time_since_robbery = time.time() - factory.last_robbery_time
        
        # Security level increases after robbery and decays over time (2 minutes)
        if time_since_robbery < 120:  # 2 minute cooldown
            # Security is strongest right after robbery, decays linearly
            cooldown_factor = 1.0 - (time_since_robbery / 120)  # 1.0 → 0.0 over 2 min
            security_reduction = factory.security_level * cooldown_factor
            actual_prob = base_prob * (1.0 - security_reduction * 0.8)  # Up to 80% reduction
        else:
            # Security has decayed, back to normal
            actual_prob = base_prob
        
        # Roll for robbery
        if random.random() > actual_prob:
            return None
        
        # Robbery successful!
        stolen_count = 0
        
        # Steal golden tickets from queues
        for queue in [factory.q_crushed, factory.q_molded, factory.q_filled, factory.q_qc]:
            items = queue._queue.copy()
            for item in items:
                if item.is_golden:
                    try:
                        queue._queue.remove(item)
                        stolen_count += 1
                    except ValueError:
                        pass
        
        # Update factory security
        factory.last_robbery_time = time.time()
        factory.total_robberies += 1
        factory.security_level = min(0.95, 0.7 + (factory.total_robberies * 0.1))  # Caps at 95%
        
        return {
            "type": "robbery",
            "factory": factory.name,
            "stolen": stolen_count,
            "golden_remaining": factory.get_wip_golden_tickets(),
            "security_level": factory.security_level,
            "msg": f"🚨 ROBBERY at {factory.name}! {stolen_count} golden tickets stolen! Security increased to {factory.security_level:.0%}",
        }

    def _vip_visit(self):
        """
        Phase 13: VIP visits grant event immunity shield.
        
        Instead of demand boost, VIP grants 60s protection from all events.
        Weighted by efficiency - better factories attract more VIPs.
        """
        if not self.factories or len(self.factories) == 0:
            return None
        
        # Weight factories by efficiency (throughput / defects)
        weights = []
        for f in self.factories:
            metrics = f.get_factory_metrics()
            efficiency = metrics.throughput_1m / (1 + metrics.defect_rate)
            weights.append(max(0.1, efficiency))  # Minimum weight
        
        total_weight = sum(weights)
        if total_weight == 0:
            factory = random.choice(self.factories)
        else:
            factory = random.choices(self.factories, weights=weights, k=1)[0]
        
        # Grant 60s shield
        shield_duration = 60
        factory.vip_shield_until = time.time() + shield_duration
        factory.vip_visit_count += 1
        
        return {
            "type": "vip_visit",
            "factory": factory.name,
            "shield_duration": shield_duration,
            "msg": f"🎩 VIP at {factory.name}! 60s event shield activated!",
        }

    def _machine_breakdown(self):
        """
        Phase 13: Machine breakdown with repair costs.
        Respects VIP shield - won't target protected factories.
        """
        if not self.factories:
            return None
        
        # Filter out VIP-shielded factories
        eligible_factories = [
            f for f in self.factories
            if time.time() > f.vip_shield_until
        ]
        
        if not eligible_factories:
            return None  # All factories protected
        
        factory = random.choice(eligible_factories)
        target_station = random.choice(["Crushing", "Molding", "Filling", "QC"])
        duration = random.randint(5, 15)
        repair_cost = random.uniform(500, 1500)
        
        # Apply repair cost to factory
        factory.breakdown_costs += repair_cost
        factory.total_cost += repair_cost
        
        return {
            "type": "machine_breakdown",
            "factory": factory.name,
            "station": target_station,
            "duration": duration,
            "repair_cost": repair_cost,
            "msg": f"⚙️ {target_station} breakdown at {factory.name}! ${repair_cost:.0f} repair, down {duration}s",
        }

    def _demand_spike(self):
        if not global_state.cities:
            return None  # Skip if no cities
        
        city = random.choice(global_state.cities)
        
        # Phase 11: Spike demand for specific bar type in a city
        from core.chocolate_type import ChocolateType
        bar_type = random.choice(ChocolateType.all_types())
        multiplier = random.uniform(1.5, 2.5)
        
        # Apply spike to city's current demand
        old_demand = city.current_demand.get(bar_type, 10.0)
        city.current_demand[bar_type] = old_demand * multiplier
        
        return {
            "type": "demand_spike",
            "city": city.name,
            "bar_type": bar_type.value,
            "multiplier": multiplier,
            "msg": f"Demand spike in {city.name} for {bar_type.value}! x{multiplier:.1f}",
        }

    def _transport_delay(self):
        """Phase 5: Logistics event - transport delays."""
        if not global_state.cities:
            return None  # Skip if no cities
        city = random.choice(global_state.cities)
        delay_factor = random.uniform(1.4, 2.5)
        return {
            "type": "transport_delay",
            "city": city.name,
            "delay_factor": delay_factor,
            "msg": f"Transport delays to {city.name}! Delivery x{delay_factor:.1f} slower",
        }
    
    def _transport_accident(self):
        """Phase 5: Logistics event - transport accidents reduce delivered quantity."""
        if not global_state.cities:
            return None  # Skip if no cities
        city = random.choice(global_state.cities)
        loss_pct = random.uniform(0.1, 0.3)  # 10-30% loss
        return {
            "type": "transport_accident",
            "city": city.name,
            "loss_percent": loss_pct,
            "msg": f"Transport accident to {city.name}! Lost {loss_pct*100:.0f}% of shipment",
        }

    def _system_boost(self):
        return {
            "type": "system_boost",
            "multiplier": random.uniform(1.1, 1.3),
            "duration": random.randint(5, 12),
            "msg": "Global performance boost active!",
        }

    # -------------------------------------------------------
    # Main loop
    # -------------------------------------------------------

    def run(self) -> None:
        while self._running:
            time.sleep(self.period)

            # 30% event chance per cycle (8 seconds)
            if random.random() > 0.30:
                continue  # no event triggered

            # Phase 5: Event type selection
            EVENT_TYPES = [
                ("vip_visit", 0.12),
                ("robbery", 0.08),
                ("machine_breakdown", 0.12),
                ("demand_spike", 0.12),         # City-specific bar type spike
                ("holiday_rush", 0.10),         # Global demand boost
                ("viral_campaign", 0.12),       # Specific bar type globally
                ("supply_shortage", 0.08),      # Reduce factory capacity
                ("weather_disruption", 0.08),   # Delay shipments
                ("cocoa_shortage", 0.10),       # Phase 13: Global cost spike
                ("transport_delay", 0.04),      # Reduced from 0.09
                ("transport_accident", 0.04),   # Reduced from 0.09
            ]
            
            event_names, weights = zip(*EVENT_TYPES)
            etype = random.choices(event_names, weights=weights, k=1)[0]

            generator = {
                "machine_breakdown": self._machine_breakdown,
                "robbery": self._robbery,
                "vip_visit": self._vip_visit,
                "demand_spike": self._demand_spike,
                "transport_delay": self._transport_delay,
                "transport_accident": self._transport_accident,
                # Phase 11: Demand-driven events
                "holiday_rush": self._holiday_rush,
                "viral_campaign": self._viral_campaign,
                "supply_shortage": self._supply_shortage,
                "weather_disruption": self._weather_disruption,
                # Phase 13: Financial events
                "cocoa_shortage": self._cocoa_shortage,
                "system_boost": self._system_boost,
            }[etype]

            event = generator()
            
            if event is None:
                continue  # Skip if generator returned None

            # Log globally
            global_state.event_log.append(event["msg"])

            # Publish
            self.event_bus.publish("global_event", event)
    
    # Phase 11: New dynamic events
    def _holiday_rush(self):
        """Global demand surge - all cities +50-100% for all bar types."""
        if not global_state.cities:
            return None
        
        from core.chocolate_type import ChocolateType
        multiplier = random.uniform(1.5, 2.0)
        
        for city in global_state.cities:
            for bar_type in ChocolateType.all_types():
                city.current_demand[bar_type] *= multiplier
        
        return {
            "type": "holiday_rush",
            "multiplier": multiplier,
            "msg": f"🎄 HOLIDAY RUSH! Global demand surged {multiplier:.1f}x across all cities!",
        }
    
    def _viral_campaign(self):
        """Viral marketing campaign boosts one bar type globally."""
        if not global_state.cities:
            return None
        
        from core.chocolate_type import ChocolateType
        bar_type = random.choice(ChocolateType.all_types())
        multiplier = random.uniform(2.5, 4.0)
        
        for city in global_state.cities:
            city.current_demand[bar_type] *= multiplier
        
        return {
            "type": "viral_campaign",
            "bar_type": bar_type.value,
            "multiplier": multiplier,
            "msg": f"📱 VIRAL! {bar_type.value} bars trending worldwide! Demand x{multiplier:.1f}!",
        }
    
    def _supply_shortage(self):
        """Temporary capacity reduction in random factory."""
        if not self.factories:
            return None
        
        factory = random.choice(self.factories)
        
        # Reduce max_workers by 30% on all scalable stations
        affected_stations = []
        for station in factory.stations:
            if hasattr(station, 'max_workers'):
                # Save original if not already saved
                if not hasattr(station, '_original_max_workers'):
                    station._original_max_workers = station.max_workers
                
                # Reduce by 30%
                station.max_workers = max(1, int(station.max_workers * 0.7))
                affected_stations.append(station.name)
        
        # Schedule restoration after 30 seconds
        def restore_capacity():
            time.sleep(30)
            for station in factory.stations:
                if hasattr(station, '_original_max_workers'):
                    station.max_workers = station._original_max_workers
                    delattr(station, '_original_max_workers')
        
        import threading
        threading.Thread(target=restore_capacity, daemon=True).start()
        
        return {
            "type": "supply_shortage",
            "factory": factory.name,
            "affected_stations": len(affected_stations),
            "msg": f"⚠️ Supply shortage at {factory.name}! Capacity -30% for 30s (affects {len(affected_stations)} stations).",
        }
    
    def _weather_disruption(self):
        """Severe weather delays shipments to/from specific city."""
        if not global_state.cities:
            return None
        
        city = random.choice(global_state.cities)
        # Note: Would increase ETAs for orders to/from this city
        
        return {
            "type": "weather_disruption",
            "city": city.name,
            "msg": f"🌪️ Severe weather at {city.name}! Shipment delays expected.",
        }

    def _cocoa_shortage(self):
        """
        Phase 13: Global cocoa crisis - massively increases production costs.
        
        Affects ALL factories for 5-10 seconds, multiplying costs by 3-5x.
        Creates dramatic negative profit moment to test financial resilience.
        """
        if not self.factories:
            return None
        
        multiplier = random.uniform(3.0, 5.0)
        duration = random.randint(5, 10)
        
        # Apply to all factories
        affected_factories = []
        for factory in self.factories:
            factory.cocoa_shortage_multiplier = multiplier
            factory.cocoa_shortage_until = time.time() + duration
            affected_factories.append(factory.name)
        
        # Schedule automatic restoration
        def restore_costs():
            time.sleep(duration)
            for factory in self.factories:
                factory.cocoa_shortage_multiplier = 1.0
                factory.cocoa_shortage_until = 0
        
        import threading
        threading.Thread(target=restore_costs, daemon=True).start()
        
        return {
            "type": "cocoa_shortage",
            "multiplier": multiplier,
            "duration": duration,
            "affected_factories": len(affected_factories),
            "msg": f"☕ COCOA SHORTAGE! Global crisis - costs x{multiplier:.1f} for {duration}s!",
        }
