import stmpy
import json
import time


BATTERY_THRESHOLD = 60.0


class DroneComponent:
    def __init__(self, drone_id, mqtt_client, battery=100.0, rotor_ok=True, sensors_ok=True, communication_ok=True):
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
        payload = {
            "drone_id": self.drone_id,
            "status": status,
            "message": message,
            "telemetry": self.telemetry,
            "timestamp": time.time(),
        }
        self.mqtt_client.publish(self.topic, json.dumps(payload))
        print(f"[MQTT] {self.drone_id} → {status}: {message}")

    def on_idle(self):
        self._publish("IDLE", "Drone idle. Awaiting diagnostic.")

    def on_diagnostic(self):
        self._publish("DIAGNOSTIC", "Running diagnostic checks...")

    def evaluate(self):
        t = self.telemetry
        time.sleep(3)
        if not t["communication_ok"]:
            self.stm.send("result_offline")
        elif t["battery"] < BATTERY_THRESHOLD:
            self.stm.send("result_charging")
        elif not t["rotor_ok"] or not t["sensors_ok"]:
            self.stm.send("result_maintenance")
        else:
            self.stm.send("result_ready")

    def on_ready(self):
        self._publish("READY", "All systems nominal. Drone ready for deployment.")

    def set_low_battery(self):
        self.telemetry["battery"] = 10.0

    def restore_battery(self):
        self.telemetry["battery"] = 100.0

    def on_charging(self):
        b = self.telemetry["battery"]
        self._publish("CHARGING", f"Battery at {b:.1f}% — charging now.")

    def on_broken(self):
        self._publish("BROKEN", "Drone reported as broken. Awaiting maintenance.")

    def on_maintenance(self):
        issues = []
        if not self.telemetry["rotor_ok"]:
            issues.append("rotor failure")
        if not self.telemetry["sensors_ok"]:
            issues.append("sensor failure")
        msg = ("Requires maintenance: " + ", ".join(issues) + ".") if issues else "Under maintenance. Repairing..."
        self._publish("MAINTENANCE", msg)

    def on_offline(self):
        self._publish("OFFLINE", "Communication failed. Drone is unreachable.")

    def on_delivering(self):
        self._publish("DELIVERING", "Drone is currently out on a delivery.")


# Transitions
t0  = {"source": "initial",              "target": "Idle"}
t1  = {"trigger": "run_diag",            "source": "Idle",        "target": "Diagnostic"}
t2  = {"trigger": "result_ready",        "source": "Diagnostic",  "target": "Ready"}
t3  = {"trigger": "result_charging",     "source": "Diagnostic",  "target": "Charging"}
t4  = {"trigger": "result_maintenance",  "source": "Diagnostic",  "target": "Maintenance"}
t5  = {"trigger": "result_offline",      "source": "Diagnostic",  "target": "Offline"}
t6  = {"trigger": "go_idle",             "source": "Ready",       "target": "Idle"}
t7  = {"trigger": "go_idle",             "source": "Charging",    "target": "Idle"}
t8  = {"trigger": "go_idle",             "source": "Maintenance", "target": "Idle"}
t9  = {"trigger": "go_idle",             "source": "Offline",     "target": "Idle"}
t10 = {"trigger": "drone_busy",          "source": "Ready",       "target": "Delivering"}
t11 = {"trigger": "drone_free",          "source": "Delivering",  "target": "Ready"}
t12 = {"trigger": "low_battery",         "source": "Ready",       "target": "Charging",    "effect": "set_low_battery"}
t13 = {"trigger": "low_battery",         "source": "Idle",        "target": "Charging",    "effect": "set_low_battery"}
t14 = {"trigger": "drone_broken",        "source": "Ready",       "target": "Broken"}
t15 = {"trigger": "drone_broken",        "source": "Idle",        "target": "Broken"}
t16 = {"trigger": "send_to_maintenance", "source": "Broken",      "target": "Maintenance"}
t17 = {"trigger": "t_charged",           "source": "Charging",    "target": "Ready",       "effect": "restore_battery"}
t18 = {"trigger": "t_repaired",          "source": "Maintenance", "target": "Ready"}

# States
idle        = {"name": "Idle",        "entry": "on_idle"}
diagnostic  = {"name": "Diagnostic",  "entry": "on_diagnostic; evaluate"}
ready       = {"name": "Ready",       "entry": "on_ready"}
charging    = {"name": "Charging",    "entry": 'on_charging; start_timer("t_charged", 3000)'}
maintenance = {"name": "Maintenance", "entry": 'on_maintenance; start_timer("t_repaired", 3000)'}
broken      = {"name": "Broken",      "entry": "on_broken"}
offline     = {"name": "Offline",     "entry": "on_offline"}
delivering  = {"name": "Delivering",  "entry": "on_delivering"}

ALL_TRANSITIONS = [t0, t1, t2, t3, t4, t5, t6, t7, t8, t9, t10, t11, t12, t13, t14, t15, t16, t17, t18]
ALL_STATES      = [idle, diagnostic, ready, charging, maintenance, broken, offline, delivering]
