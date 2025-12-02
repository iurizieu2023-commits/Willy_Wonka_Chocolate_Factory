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
    
    Publishes to EventBus as "global_event" with a data payload including:
        {
            "type": "robbery" | "vip_visit" | "transport_delay" | ...,
            "msg":  "<human readable message>",
            ...
        }
    """
    def __init__(
        self,
        event_bus: EventBus,
        factories: List["Factory"] | None = None,
        period: float = 8.0,
    ) -> None:
        super().__init__(name="EventEngine", daemon=True)
        self.event_bus = event_bus
        self.factories = factories or []
        self.period = period
        self._running = True

        # Phase 5: Track golden ticket count per factory for robbery probability
        self._golden_count: dict[str, int] = {}

    def stop(self) -> None:
        self._running = False

    def set_factories(self, factories: List["Factory"]) -> None:
        """Set factories to monitor (can be called after __init__)."""
        self.factories = factories

    # -------------------------------------------------------
    # Phase 5: Probabilistic event generators
    # -------------------------------------------------------

    def _calculate_robbery_probability(self, factory: "Factory") -> float:
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
        return min(0.70, 0.02 + (wip_golden**2) * 0.08)

    def _calculate_vip_probability(self, factory: "Factory") -> float:
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
            f
            for f in self.factories
            if time.time() > f.vip_shield_until and f.get_wip_golden_tickets() > 0
        ]

        if not eligible_factories:
            return None  # All factories either protected or have no golden tickets

        # Sort by golden ticket count (descending)
        eligible_factories.sort(
            key=lambda f: f.get_wip_golden_tickets(), reverse=True
        )
        factory = eligible_factories[0]
        wip_golden = factory.get_wip_golden_tickets()

        # Calculate base robbery probability from golden tickets
        base_prob = self._calculate_robbery_probability(factory)

        # Apply security cooldown - reduces probability if recently robbed
        import time

        if not hasattr(factory, "last_robbery_time"):
            factory.last_robbery_time = 0.0
        if not hasattr(factory, "security_level"):
            factory.security_level = 0.0  # 0.0–1.0, higher = more secure

        time_since_last = time.time() - factory.last_robbery_time

        # Security decays over time
        security_decay = min(time_since_last / 120.0, 1.0)  # full decay over 2 minutes
        factory.security_level = max(0.0, factory.security_level - security_decay)

        # Security reduction factor (0–0.5)
        security_reduction = min(factory.security_level * 0.5, 0.5)

        # Effective probability
        actual_prob = base_prob * (1.0 - security_reduction)

        # Roll for robbery
        if random.random() > actual_prob:
            return None

        # Robbery successful!
        stolen_count = 0

        # Steal golden tickets from queues
        for queue in [
            factory.q_crushed,
            factory.q_molded,
            factory.q_filled,
            factory.q_qc,
        ]:
            items = queue._queue.copy()
            for item in items:
                if item.is_golden:
                    try:
                        queue._queue.remove(item)
                        stolen_count += 1
                    except ValueError:
                        pass

        # Update last robbery time and security
        factory.last_robbery_time = time.time()
        factory.security_level = min(factory.security_level + 0.3, 1.0)

        if stolen_count == 0:
            return None

        return {
            "type": "robbery",
            "factory": factory.name,
            "stolen": stolen_count,
            "msg": f"🚨 ROBBERY at {factory.name}! {stolen_count} golden tickets stolen!",
        }

    def _vip_visit(self):
        """
        Phase 13: VIP visit can grant temporary immunity to robberies and breakdowns.
        """
        if not self.factories:
            return None

        # Choose factory with highest efficiency
        best_factory = None
        best_efficiency = -1.0

        for f in self.factories:
            metrics = f.get_factory_metrics()
            efficiency = metrics.throughput_1m / (1 + metrics.defect_rate)
            if efficiency > best_efficiency:
                best_efficiency = efficiency
                best_factory = f

        if not best_factory:
            return None

        factory = best_factory

        # Probability of VIP visit based on efficiency
        base_prob = self._calculate_vip_probability(factory)

        if random.random() > base_prob:
            return None

        # VIP visit triggers temporary event shield (no robberies or breakdowns)
        shield_duration = random.randint(30, 60)
        factory.vip_shield_until = time.time() + shield_duration
        factory.vip_visit_count += 1

        # Boost demand in the local city (if exists)
        local_city = None
        if global_state.cities:
            # Find city with same name or close coordinates
            for city in global_state.cities:
                if city.name in factory.name: # e.g. Wonka-London -> London
                    local_city = city
                    break
        
        if local_city:
            for key in local_city.current_demand:
                local_city.current_demand[key] *= 1.5
            print(
                f"{global_state.Color.GREEN}🌟 VIP VISIT at {factory.name}: "
                f"Local demand in {local_city.name} boosted x1.5!{global_state.Color.RESET}"
            )
        else:
             print(
                f"{global_state.Color.GREEN}🌟 VIP VISIT at {factory.name}: "
                f"Prestige increased!{global_state.Color.RESET}"
            )

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
            f for f in self.factories if time.time() > f.vip_shield_until
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
        duration = random.randint(45, 90)  # Increased for visibility
        
        # Apply delay to city
        city.weather_disruption_until = time.time() + duration
        city.weather_disruption_multiplier = delay_factor
        
        return {
            "type": "transport_delay",
            "city": city.name,
            "delay_factor": delay_factor,
            "duration": duration,
            "msg": f"Transport delays to {city.name}! Delivery x{delay_factor:.1f} slower for {duration}s",
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
        """Main loop: periodically spawn events."""
        while self._running:
            time.sleep(self.period)

            if not self.factories:
                continue

            # Phase 5: Roll for any event to occur this period
            # Increase global event frequency so the Supervisor has more to do
            # Old behavior: ~30% chance to trigger any event each cycle
            # New behavior: ~60% chance, so events (esp. breakdowns) are more visible
            if random.random() > 0.60:
                continue  # no event triggered

            # Phase 5: Event type selection
            # Tuned event mix: machine_breakdown is now more likely so the
            # Supervisor and repair logic are actively exercised during runs.
            EVENT_TYPES = [
                ("vip_visit", 0.10),
                ("robbery", 0.06),
                ("machine_breakdown", 0.25),  # was 0.12
                ("demand_spike", 0.10),  # City-specific bar type spike
                ("holiday_rush", 0.08),  # Global demand boost
                ("viral_campaign", 0.10),  # Specific bar type globally
                ("supply_shortage", 0.07),  # Reduce factory capacity
                ("weather_disruption", 0.12),  # Increased from 0.07
                ("cocoa_shortage", 0.07),  # Phase 13: Global cost spike
                ("transport_delay", 0.10),  # Increased from 0.05
                ("transport_accident", 0.20),  # Reduced slightly
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
                # Phase 13: Cocoa shortage
                "cocoa_shortage": self._cocoa_shortage,
                # System-wide boost
                "system_boost": self._system_boost,
            }[etype]

            event = generator()

            if event is None:
                continue  # Skip if generator returned None

            # Log globally
            global_state.event_log.append(event["msg"])

            # Publish
            self.event_bus.publish("global_event", event)

            # Handle logistics events directly
            if event["type"] == "transport_accident":
                city_name = event.get("city")
                loss_pct = event.get("loss_percent", 0.1)

                # Apply spoilage to shipments
                
                # The DemandEngine instance is stored globally in simulation via global_state
                if hasattr(global_state, "demand_engine") and global_state.demand_engine:
                    global_state.demand_engine.apply_transport_accident(city_name, loss_pct)


    # Phase 11: New dynamic events

    def _holiday_rush(self):
        """Global increase in demand for all factories."""
        if not self.factories:
            return None

        duration = random.randint(20, 40)
        multiplier = random.uniform(1.3, 1.8)

        for city in global_state.cities:
            for key in city.current_demand:
                city.current_demand[key] *= multiplier

        return {
            "type": "holiday_rush",
            "duration": duration,
            "multiplier": multiplier,
            "msg": f"🎄 Holiday rush! Global demand x{multiplier:.1f} for {duration}s",
        }

    def _viral_campaign(self):
        """Global demand spike for a specific bar type."""
        if not self.factories:
            return None

        from core.chocolate_type import ChocolateType

        bar_type = random.choice(ChocolateType.all_types())
        multiplier = random.uniform(1.5, 2.5)

        for factory in self.factories:
            factory.target_mix[bar_type] *= multiplier

        return {
            "type": "viral_campaign",
            "bar_type": bar_type.value,
            "multiplier": multiplier,
            "msg": f"📢 Viral campaign for {bar_type.value}! Target mix x{multiplier:.1f}",
        }

    def _supply_shortage(self):
        """Reduce effective capacity for a random factory."""
        if not self.factories:
            return None

        factory = random.choice(self.factories)
        capacity_reduction = random.uniform(0.2, 0.5)  # 20-50% reduction

        factory.capacity_factor = max(
            0.1, 1.0 - capacity_reduction
        )  # track capacity if implemented

        return {
            "type": "supply_shortage",
            "factory": factory.name,
            "capacity_reduction": capacity_reduction,
            "msg": f"📉 Supply shortage at {factory.name}! Capacity -{capacity_reduction*100:.0f}%",
        }

    def _weather_disruption(self):
        """Slow down logistics (deliveries)."""
        if not global_state.cities:
            return None

        city = random.choice(global_state.cities)
        delay_factor = random.uniform(1.3, 2.0)
        duration = random.randint(60, 120)  # Increased for visibility
        
        # Apply disruption to city
        city.weather_disruption_until = time.time() + duration
        city.weather_disruption_multiplier = delay_factor

        return {
            "type": "weather_disruption",
            "city": city.name,
            "delay_factor": delay_factor,
            "duration": duration,
            "msg": f"🌧️ Weather disruption in {city.name}! Deliveries x{delay_factor:.1f} slower for {duration}s",
        }

    def _cocoa_shortage(self):
        """Phase 13: Global cocoa shortage increases costs."""
        if not self.factories:
            return None

        duration = random.randint(30, 60)
        multiplier = random.uniform(1.5, 2.5)

        affected_factories = random.sample(
            self.factories, k=max(1, len(self.factories) // 2)
        )

        for factory in affected_factories:
            factory.cocoa_shortage_multiplier = multiplier
            factory.cocoa_shortage_until = time.time() + duration

        def restore_costs():
            time.sleep(duration)
            for factory in affected_factories:
                if time.time() >= factory.cocoa_shortage_until:
                    factory.cocoa_shortage_multiplier = 1.0
                    factory.cocoa_shortage_until = 0

        threading.Thread(target=restore_costs, daemon=True).start()

        return {
            "type": "cocoa_shortage",
            "multiplier": multiplier,
            "duration": duration,
            "affected_factories": len(affected_factories),
            "msg": f"☕ COCOA SHORTAGE! Global crisis - costs x{multiplier:.1f} for {duration}s!",
        }
