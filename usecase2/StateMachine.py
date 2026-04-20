import json
import time


class PackageDeliveryComponent:
    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client
        self.drone_id    = None
        self.package_id  = None
        self.telemetry   = {"battery": 100, "speed": 0, "eta": "Calculating..."}

    @property
    def topic(self):
        return f"delivery/{self.package_id or 'unknown'}/status"

    def _publish(self, state_name):
        self.mqtt_client.publish(self.topic, json.dumps({
            "package_id": self.package_id,
            "drone_id":   self.drone_id,
            "status":     state_name,
            "telemetry":  self.telemetry,
            "timestamp":  time.time(),
        }))

    def on_idle(self):
        self.telemetry["speed"] = 0
        self._publish("Idle")

    def on_notice(self):
        self._publish("Notice of package")

    def on_pickup_ready(self):
        self._publish("Ready for drone pickup")

    def on_transport(self):
        self.telemetry["speed"]   = 45
        self.telemetry["battery"] -= 5
        self.telemetry["eta"]     = "12 mins"
        self._publish("In transport")

    def on_delivery_place(self):
        self.telemetry["speed"] = 0
        self.telemetry["eta"]   = "Arrived"
        self._publish("At delivery place")

    def on_return(self):
        self.telemetry["speed"] = 45
        self.telemetry["eta"]   = "Returning..."
        self._publish("Return to sender")

    def remove_package(self):
        print(f"[UC2] Package {self.package_id} complete.")


UC2_TRANSITIONS = [
    {"source": "initial",            "target": "Idle"},
    {"trigger": "package_sent",      "source": "Idle",                   "target": "Notice of package"},
    {"trigger": "package_at_pickup", "source": "Notice of package",      "target": "Ready for drone pickup"},
    {"trigger": "picked_up",         "source": "Ready for drone pickup", "target": "In transport"},
    {"trigger": "dropped_off",       "source": "In transport",           "target": "At delivery place"},
    {"trigger": "delivered",         "source": "At delivery place",      "target": "Idle", "effect": "remove_package"},
    {"trigger": "t",                 "source": "At delivery place",      "target": "Return to sender"},
    {"trigger": "returned",          "source": "Return to sender",       "target": "Idle", "effect": "remove_package"},
]

UC2_STATES = [
    {"name": "Idle",                   "entry": "on_idle"},
    {"name": "Notice of package",      "entry": "on_notice"},
    {"name": "Ready for drone pickup", "entry": "on_pickup_ready"},
    {"name": "In transport",           "entry": "on_transport"},
    {"name": "At delivery place",      "entry": 'on_delivery_place; start_timer("t", 8000)'},
    {"name": "Return to sender",       "entry": "on_return"},
]
