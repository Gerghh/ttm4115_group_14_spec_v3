import json
import time

BATTERY_THRESHOLD = 60.0


class DroneComponent:
    def __init__(self, drone_id, mqtt_client, battery=100.0,
                 rotor_ok=True, sensors_ok=True, communication_ok=True):
        self.drone_id = drone_id
        self.mqtt_client = mqtt_client
        self.topic = f"drone/{drone_id}/status"
        self.telemetry = {
            "battery": battery,
            "rotor_ok": rotor_ok,
            "sensors_ok": sensors_ok,
            "communication_ok": communication_ok,
        }

    def _publish(self, status, message):
        self.mqtt_client.publish(self.topic, json.dumps({
            "drone_id": self.drone_id,
            "status": status,
            "message": message,
            "telemetry": self.telemetry,
            "timestamp": time.time(),
        }))

    def on_idle(self):       self._publish("IDLE",       "Drone idle.")
    def on_diagnostic(self): self._publish("DIAGNOSTIC", "Running checks...")
    def on_ready(self):      self._publish("READY",      "All systems nominal. Ready for deployment.")
    def on_delivering(self): self._publish("DELIVERING", "Out on a delivery.")

    def on_charging(self):
        self._publish("CHARGING", f"Battery at {self.telemetry['battery']:.1f}% — charging.")

    def on_maintenance(self):
        issues = []
        if not self.telemetry["rotor_ok"]:   issues.append("rotor failure")
        if not self.telemetry["sensors_ok"]: issues.append("sensor failure")
        self._publish("MAINTENANCE", "Requires maintenance: " + ", ".join(issues) + ".")

    def on_offline(self):
        self._publish("OFFLINE", "Communication failed. Drone unreachable.")

    def evaluate(self):
        t = self.telemetry
        if not t["communication_ok"]:                   self.stm.send("result_offline")
        elif t["battery"] < BATTERY_THRESHOLD:          self.stm.send("result_charging")
        elif not t["rotor_ok"] or not t["sensors_ok"]: self.stm.send("result_maintenance")
        else:                                            self.stm.send("result_ready")


UC1_TRANSITIONS = [
    {"source": "initial",             "target": "Idle"},
    {"trigger": "run_diag",           "source": "Idle",        "target": "Diagnostic", "effect": "on_diagnostic; evaluate"},
    {"trigger": "result_ready",       "source": "Diagnostic",  "target": "Ready"},
    {"trigger": "result_charging",    "source": "Diagnostic",  "target": "Charging"},
    {"trigger": "result_maintenance", "source": "Diagnostic",  "target": "Maintenance"},
    {"trigger": "result_offline",     "source": "Diagnostic",  "target": "Offline"},
    {"trigger": "go_idle",            "source": "Ready",       "target": "Idle"},
    {"trigger": "go_idle",            "source": "Charging",    "target": "Idle"},
    {"trigger": "go_idle",            "source": "Maintenance", "target": "Idle"},
    {"trigger": "go_idle",            "source": "Offline",     "target": "Idle"},
    {"trigger": "drone_busy",         "source": "Ready",       "target": "Delivering"},
    {"trigger": "drone_free",         "source": "Delivering",  "target": "Ready"},
]

UC1_STATES = [
    {"name": "Idle",        "entry": "on_idle"},
    {"name": "Diagnostic",  "entry": "on_diagnostic"},
    {"name": "Ready",       "entry": "on_ready"},
    {"name": "Charging",    "entry": "on_charging"},
    {"name": "Maintenance", "entry": "on_maintenance"},
    {"name": "Offline",     "entry": "on_offline"},
    {"name": "Delivering",  "entry": "on_delivering"},
]
