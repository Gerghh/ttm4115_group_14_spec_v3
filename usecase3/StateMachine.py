import json
import time
import random
import string


class OrderProcessComponent:
    def __init__(self, mqtt_client, get_ready_drone=None, on_order_confirmed=None):
        self.mqtt_client        = mqtt_client
        self.get_ready_drone    = get_ready_drone    or (lambda: "Drone-Alpha")
        self.on_order_confirmed = on_order_confirmed or (lambda order: None)
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
        self.order["location"]         = location
        self.order["measurements"]     = measurements
        self.order["personal_info"]    = personal_info
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
        self._publish("FINDING_DRONE", f"Found available drone: {drone}.")
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
