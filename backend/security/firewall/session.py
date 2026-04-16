from .middleware import FirewallMiddleware

class FirewallSession:
    def __init__(self, app):
        self.app = app

    def initialize(self):
        self.app.add_middleware(FirewallMiddleware)
        return self
