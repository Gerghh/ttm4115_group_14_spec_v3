import stmpy
import json
import time
import random
import string

BATTERY_THRESHOLD = 60.0


# ══════════════════════════════════════════════════════════════════════
# UC-1  Drone Fleet Diagnostics
# ══════════════════════════════════════════════════════════════════════

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
    {"source": "initial",              "target": "Idle"},
    {"trigger": "run_diag",            "source": "Idle",        "target": "Diagnostic", "effect": "on_diagnostic; evaluate"},
    {"trigger": "result_ready",        "source": "Diagnostic",  "target": "Ready"},
    {"trigger": "result_charging",     "source": "Diagnostic",  "target": "Charging"},
    {"trigger": "result_maintenance",  "source": "Diagnostic",  "target": "Maintenance"},
    {"trigger": "result_offline",      "source": "Diagnostic",  "target": "Offline"},
    {"trigger": "go_idle",             "source": "Ready",       "target": "Idle"},
    {"trigger": "go_idle",             "source": "Charging",    "target": "Idle"},
    {"trigger": "go_idle",             "source": "Maintenance", "target": "Idle"},
    {"trigger": "go_idle",             "source": "Offline",     "target": "Idle"},
    {"trigger": "drone_busy",          "source": "Ready",       "target": "Delivering"},
    {"trigger": "drone_free",          "source": "Delivering",  "target": "Ready"},
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


# ══════════════════════════════════════════════════════════════════════
# UC-2  Package Delivery
# ══════════════════════════════════════════════════════════════════════

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
    {"source": "initial",              "target": "Idle"},
    {"trigger": "package_sent",        "source": "Idle",                   "target": "Notice of package"},
    {"trigger": "package_at_pickup",   "source": "Notice of package",      "target": "Ready for drone pickup"},
    {"trigger": "picked_up",           "source": "Ready for drone pickup",  "target": "In transport"},
    {"trigger": "dropped_off",         "source": "In transport",            "target": "At delivery place"},
    {"trigger": "delivered",           "source": "At delivery place",       "target": "Idle", "effect": "remove_package"},
    {"trigger": "t",                   "source": "At delivery place",       "target": "Return to sender"},
    {"trigger": "returned",            "source": "Return to sender",        "target": "Idle", "effect": "remove_package"},
]

UC2_STATES = [
    {"name": "Idle",                   "entry": "on_idle"},
    {"name": "Notice of package",      "entry": "on_notice"},
    {"name": "Ready for drone pickup", "entry": "on_pickup_ready"},
    {"name": "In transport",           "entry": "on_transport"},
    {"name": "At delivery place",      "entry": 'on_delivery_place; start_timer("t", 8000)'},
    {"name": "Return to sender",       "entry": "on_return"},
]


# ══════════════════════════════════════════════════════════════════════
# UC-3  Order Registration
# ══════════════════════════════════════════════════════════════════════

class OrderProcessComponent:
    def __init__(self, mqtt_client, get_ready_drone=None, on_order_confirmed=None):
        self.mqtt_client         = mqtt_client
        self.get_ready_drone     = get_ready_drone    or (lambda: "Drone-Alpha")
        self.on_order_confirmed  = on_order_confirmed or (lambda order: None)
        self.topic = "order/status"
        self.order = self._empty_order()

    def _empty_order(self):
        return {
            "tracking_number":  None,
            "personal_info":    {},
            "location":         {},
            "measurements":     {},
            "payment_attempts": 0,
            "assigned_drone":   None,
            "candidate_drone":  None,
        }

    def _publish(self, status, message):
        self.mqtt_client.publish(self.topic, json.dumps({
            "status":    status,
            "message":   message,
            "order":     self.order,
            "timestamp": time.time(),
        }))

    def information(self, location, measurements, personal_info):
        self.order["location"]      = location
        self.order["measurements"]  = measurements
        self.order["personal_info"] = personal_info
        self.order["payment_attempts"] = 0

    def process_payment(self):
        self.order["payment_attempts"] += 1
        self._publish("CONFIRMING_PAYMENT",
                      f"Processing payment — attempt {self.order['payment_attempts']}.")

    def create_order(self):
        self.order["tracking_number"] = "TRK-" + "".join(
            random.choices(string.ascii_uppercase + string.digits, k=8))
        self._publish("CREATE_ORDER",
                      f"Order created. Tracking #: {self.order['tracking_number']}.")

    def assign_track_num(self):
        self.stm.send("order_created")

    def find_delivery_drone(self):
        drone = self.get_ready_drone()
        self.order["candidate_drone"] = drone
        self._publish("FINDING_DRONE", f"Searching for available drone... found {drone}.")
        self.stm.send("available_drone_found")

    def assign_delivery(self):
        self.order["assigned_drone"] = self.order["candidate_drone"]
        self._publish("PREPARING_DRONE",
                      f"Drone {self.order['assigned_drone']} assigned and preparing for pickup.")
        self.stm.send("drone_sent")

    def send_confirmation(self):
        snapshot = dict(self.order)
        self._publish("IDLE",
                      f"Order {snapshot['tracking_number']} confirmed. "
                      f"Drone {snapshot['assigned_drone']} dispatched.")
        self.on_order_confirmed(snapshot)
        self.order = self._empty_order()

    def on_idle(self):
        self._publish("IDLE", "No active order. Awaiting new registration.")


UC3_TRANSITIONS = [
    {"source": "initial",                "target": "No order"},
    {"trigger": "order_sent",            "source": "No order",           "target": "Confirming payment"},
    {"trigger": "payment_failed",        "source": "Confirming payment", "target": "No order"},
    {"trigger": "payment_confirmed",     "source": "Confirming payment", "target": "Create order"},
    {"trigger": "order_created",         "source": "Create order",       "target": "Finding drone"},
    {"trigger": "available_drone_found", "source": "Finding drone",      "target": "Preparing drone"},
    {"trigger": "drone_sent",            "source": "Preparing drone",    "target": "No order", "effect": "send_confirmation"},
]

UC3_STATES = [
    {"name": "No order",           "entry": "on_idle"},
    {"name": "Confirming payment", "entry": "process_payment"},
    {"name": "Create order",       "entry": "create_order; assign_track_num"},
    {"name": "Finding drone",      "entry": "find_delivery_drone"},
    {"name": "Preparing drone",    "entry": "assign_delivery"},
]
