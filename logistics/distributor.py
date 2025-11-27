class Distributor:
    def __init__(self, routing_strategy):
        self.routing_strategy = routing_strategy

    def distribute(self, factories, cities):
        return self.routing_strategy.route(factories, cities)
