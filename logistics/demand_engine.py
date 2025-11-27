# logistics/demand_engine.py

import threading
import time
import random
from typing import List, Optional
from logistics.city import City
from logistics.order import Order
from core.chocolate_type import ChocolateType
from observers.event_bus import EventBus


class DemandEngine(threading.Thread):
    """
    Background thread that generates orders based on city demand.
    
    Periodically:
    1. Updates city.current_demand via CityDemandStrategy
    2. Generates orders based on current_demand
    3. Assigns orders to factories (round-robin)
    4. Publishes order events via EventBus
    """
    
    def __init__(
        self,
        event_bus: EventBus,
        cities: List[City],
        factories: List = None,  # List of Factory objects
        period: float = 3.0,  # Update interval in seconds
        order_rate: float = 0.3,  # Probability of generating order per city per cycle
        routing_strategy=None,  # Phase 11: Routing strategy
        db_manager=None  # Phase 13: Database logging
    ):
        super().__init__(name="DemandEngine", daemon=True)
        self.event_bus = event_bus
        self.cities = cities
        self.factories = factories or []
        self.period = period
        self.order_rate = order_rate
        
        # Phase 11: Routing strategy
        if routing_strategy is None:
            from strategies.routing_strategy import BalancedRoutingStrategy
            routing_strategy = BalancedRoutingStrategy()
        self.routing_strategy = routing_strategy
        
        self.db_manager = db_manager  # Store for logging
        
        self._running = True
        self.orders: List[Order] = []  # Track all orders
        self._factory_assignment_index = 0  # Round-robin index
    
    def stop(self):
        """Stop the demand engine."""
        self._running = False
    
    def run(self) -> None:
        """Main loop: update demand and generate orders."""
        while self._running:
            time.sleep(self.period)
            
            try:
                # Update city demand using strategies
                for city in self.cities:
                    if city.demand_strategy:
                        city.demand_strategy.update_demand(city, self.period)
                    
                    # Phase 13: Log demand snapshot
                    if self.db_manager:
                        city_id = self.db_manager.city_ids.get(city.name)
                        if city_id:
                            # Calculate total demand rate
                            total_demand = sum(city.current_demand.values())
                            demand_rate_units_h = total_demand * (3600 / self.period)  # Convert to hourly
                            
                            from database.db_insertions_extended import insert_demand_snapshot
                            import json
                            extras = json.dumps({
                                'demand_by_type': {k.value: v for k, v in city.current_demand.items()}
                            })
                            insert_demand_snapshot(
                                city_id=city_id,
                                demand_rate_units_h=demand_rate_units_h,
                                extras=extras
                            )
                
                # Generate orders based on demand
                for city in self.cities:
                    if random.random() < self.order_rate:
                        self._generate_orders_for_city(city)
                
                # Update order statuses (simulate deliveries)
                self._update_order_statuses()
            except Exception as e:
                print(f"Error in DemandEngine loop: {e}")
    
    def _generate_orders_for_city(self, city: City) -> None:
        """Generate orders for a city based on current_demand."""
        for bar_type in ChocolateType.all_types():
            demand = city.current_demand.get(bar_type, 0)
            
            # Convert demand to order probability
            # Higher demand = higher chance of order
            order_probability = min(0.8, demand / 20.0)  # Scale: 10 demand = 50% chance
            
            if random.random() < order_probability:
                # Generate order quantity based on demand
                base_quantity = int(demand * random.uniform(0.5, 1.5))
                quantity = max(5, min(50, base_quantity))  # Clamp to [5, 50]
                
                order = Order(
                    city_name=city.name,
                    bar_type=bar_type,
                    quantity=quantity,
                    created_at=time.time(),
                    eta=0,  # Will be set after factory assignment
                    status="PENDING"
                )
                
                # Phase 11: Assign to factory using routing strategy
                if self.factories:
                    factory = self.routing_strategy.assign_factory(
                        order, 
                        self.factories, 
                        city.lat, 
                        city.lon
                    )
                    
                    if factory:
                        order.assigned_factory = factory.name
                        
                        # Calculate distance-based ETA
                        from utils.geography import haversine_distance, delivery_time
                        distance = haversine_distance(factory.lat, factory.lon, city.lat, city.lon)
                        order.eta = time.time() + delivery_time(distance)
                        
                        # Update factory backlog
                        factory.backlog_by_type[bar_type] += quantity
                        
                        # Phase 13: Log shipment start to database
                        if self.db_manager:
                            order.shipment_id = self.db_manager.log_shipment_start(order)
                            
                            # Phase 13: Log routing decision
                            city_id = self.db_manager.city_ids.get(city.name)
                            if city_id:
                                from database.db_insertions_extended import insert_routing_decision
                                import json
                                inputs = json.dumps({
                                    'distance_km': distance,
                                    'factory_backlog': factory.total_backlog(),
                                    'strategy': self.routing_strategy.__class__.__name__
                                })
                                insert_routing_decision(
                                    policy_name=self.routing_strategy.__class__.__name__,
                                    inputs=inputs,
                                    chosen_city_id=city_id,
                                    qty=quantity
                                )
                    else:
                        # Fallback: default ETA
                        order.eta = time.time() + 30.0
                else:
                    order.eta = time.time() + 30.0

                
                # Update city tracking
                city.orders_open[bar_type] += quantity
                
                # Track order
                self.orders.append(order)
                
                # Publish event
                self.event_bus.publish("order_created", {
                    "city": city.name,
                    "bar_type": bar_type.value,
                    "quantity": quantity,
                    "factory": order.assigned_factory,
                })
    
    def _update_order_statuses(self) -> None:
        """Update order statuses and simulate deliveries."""
        current_time = time.time()
        
        for order in self.orders:
            if order.status == "PENDING":
                # Check if it should be in transit
                if current_time > order.created_at + 5:  # 5s delay before transit
                    order.status = "IN_TRANSIT"
                    
                    # Find city
                    city = next((c for c in self.cities if c.name == order.city_name), None)
                    if city:
                        city.shipments_in_transit[order.bar_type] += order.quantity
            
            elif order.status == "IN_TRANSIT":
                # Check if city has weather disruption active
                city = next((c for c in self.cities if c.name == order.city_name), None)
                
                if city and hasattr(city, 'weather_disruption_until'):
                    if current_time < city.weather_disruption_until:
                        # Order is delayed by weather - extend ETA if not already done
                        if not hasattr(order, '_weather_delayed'):
                            order.eta *= city.weather_disruption_multiplier
                            order._weather_delayed = True
                            city.shipments_delayed[order.bar_type] += order.quantity
                        continue  # Don't deliver yet, still delayed
                
                # Check if ready to deliver
                if current_time >= order.eta:
                    # Deliver the order
                    order.status = "DELIVERED"
                    lead_time = current_time - order.created_at
                    transit_time_s = int(lead_time)
                    
                    # Update city metrics
                    if city:
                        city.orders_open[order.bar_type] = max(0, city.orders_open[order.bar_type] - order.quantity)
                        city.shipments_in_transit[order.bar_type] = max(0, city.shipments_in_transit[order.bar_type] - order.quantity)
                        
                        # Clear delayed if it was delayed
                        if hasattr(order, '_weather_delayed'):
                            city.shipments_delayed[order.bar_type] = max(0, city.shipments_delayed[order.bar_type] - order.quantity)
                        
                        # Track lead times
                        city.total_shipments += 1
                        city.total_lead_time += lead_time
                        
                        # Phase 13: Log shipment arrival to database
                        if self.db_manager and hasattr(order, 'shipment_id'):
                            self.db_manager.log_shipment_arrival(order, transit_time_s)
                    
                    # Update factory backlog (fulfilled)
                    if order.assigned_factory:
                        factory = next((f for f in self.factories if f.name == order.assigned_factory), None)
                        if factory:
                            factory.backlog_by_type[order.bar_type] = max(
                                0, 
                                factory.backlog_by_type[order.bar_type] - order.quantity
                            )
                    
                    # Publish delivery event
                    self.event_bus.publish("order_delivered", {
                        "city": order.city_name,
                        "bar_type": order.bar_type.value,
                        "quantity": order.quantity,
                        "lead_time": order.lead_time(),
                    })
