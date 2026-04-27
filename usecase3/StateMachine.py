import stmpy
import json
import time
import random
import string


class OrderProcessComponent:
    def __init__(self, mqtt_client):
        self.mqtt_client = mqtt_client
        self.topic = "order/status"

        self.order = {
            "tracking_number": None,
            "personal_info": {},
            "location": {},
            "measurements": {},
            "payment_attempts": 0,
            "assigned_drone": None,
        }

    def _publish(self, status, message):
        payload = {
            "status": status,
            "message": message,
            "order": self.order,
            "timestamp": time.time(),
        }
        self.mqtt_client.publish(self.topic, json.dumps(payload))
        print(f"[MQTT] → {status}: {message}")

    def information(self, location, measurements, personal_info):
        self.order["location"] = location
        self.order["measurements"] = measurements
        self.order["personal_info"] = personal_info
        self.order["payment_attempts"] = 0
        print(f"[ORDER] Details received for {personal_info.get('name', '?')}")

    def payment(self):
        print("[ORDER] Initiating payment...")

    def process_payment(self):
        self.order["payment_attempts"] += 1
        print(f"[PAYMENT] Processing payment (attempt {self.order['payment_attempts']})...")
        self._publish("CONFIRMING_PAYMENT", f"Processing payment — attempt {self.order['payment_attempts']}.")

    def create_order(self):
        self.order["tracking_number"] = "TRK-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=8))
        print(f"[ORDER] Order created. Tracking number: {self.order['tracking_number']}")
        self._publish("CREATE_ORDER", f"Order created. Assigning tracking number {self.order['tracking_number']}.")

    def assign_track_num(self):
        print(f"[ORDER] Tracking number {self.order['tracking_number']} assigned.")
        self.stm.send("order_created")

    def find_delivery_drone(self):
        print(f"[DRONE] Searching for available drone near {self.order['location'].get('pickup', '?')}...")
        time.sleep(3)
        self._publish("FINDING_DRONE", "Searching for an available drone for this delivery route.")

    def assign_delivery(self):
        drone_id = f"DRONE-{random.randint(1, 99):02d}"
        self.order["assigned_drone"] = drone_id
        
        print(f"[DRONE] Drone {drone_id} assigned. Preparing delivery.")
        self._publish("PREPARING_DRONE", f"Drone {drone_id} assigned and preparing for pickup.")

    def send_confirmation(self):
        print(f"[ORDER] Confirmation sent to {self.order['personal_info'].get('email', '?')}.")
        self._publish("IDLE", f"Order {self.order['tracking_number']} confirmed. Drone {self.order['assigned_drone']} dispatched.")
        self.order = {
            "tracking_number": None,
            "personal_info": {},
            "location": {},
            "measurements": {},
            "payment_attempts": 0,
            "assigned_drone": None,
        }

    def on_idle(self):
        self._publish("IDLE", "No active order. Awaiting new registration.")


t0 = {"source": "initial",              "target": "No order"}
t1 = {"trigger": "order_sent",          "source": "No order",          "target": "Confirming payment"}
t2 = {"trigger": "payment_failed",      "source": "Confirming payment", "target": "No order"}
t3 = {"trigger": "payment_confirmed",   "source": "Confirming payment", "target": "Create order"}
t4 = {"trigger": "order_created",       "source": "Create order",       "target": "Finding drone"}
t5 = {"trigger": "available_drone_found","source": "Finding drone",     "target": "Preparing drone"}
t6 = {"trigger": "drone_sent",          "source": "Preparing drone",    "target": "No order",   "effect": "send_confirmation"}

idle        = {"name": "No order",          "entry": "on_idle"}
confirming  = {"name": "Confirming payment","entry": "process_payment"}
create      = {"name": "Create order",      "entry": "create_order; assign_track_num"}
finding     = {"name": "Finding drone",     "entry": "find_delivery_drone"}
preparing   = {"name": "Preparing drone",   "entry": "assign_delivery"}

UC3_TRANSITIONS = [t0, t1, t2, t3, t4, t5, t6]
UC3_STATES = [idle, confirming, create, finding, preparing]
