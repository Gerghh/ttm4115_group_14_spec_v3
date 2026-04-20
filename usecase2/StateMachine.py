import stmpy
import logging
import json
import time

class PackageDeliveryComponent:
    def __init__(self, package_id, mqtt_client):
        self.package_id = package_id
        self.mqtt_client = mqtt_client
        self.topic = f"delivery/{package_id}/status"
        
        # Telemetry data storage (from UC-2)
        self.telemetry = {
            "pos": [0.0, 0.0],
            "battery": 100,
            "speed": 0,
            "eta": "Calculating..."
        }

    def _publish_update(self, state_name):
        """Sends a JSON payload over MQTT representing the current system state."""
        payload = {
            "package_id": self.package_id,
            "status": state_name,
            "telemetry": self.telemetry,
            "timestamp": time.time()
        }
        self.mqtt_client.publish(self.topic, json.dumps(payload))
        print(f"[MQTT] Published status: {state_name}")

    # Entry actions defined in the STM
    def on_idle(self):
        print("System Idle. Waiting for package...")

    def on_notice(self):
        self._publish_update("Notice of package")
        
    def on_pickup_ready(self):
        self._publish_update("Ready for drone pickup")

    def on_transport(self):
        # UC-2: Simulating telemetry update
        self.telemetry["speed"] = 15 
        self._publish_update("In transport")

    def on_delivery_place(self):
        self._publish_update("At delivery place")

    def on_return(self):
        self._publish_update("Return to sender")

    def remove_package(self):
        print(f"Cleaning up resources for {self.package_id}")

# Define the transitions from your diagram
t0 = {'source': 'initial', 'target': 'Idle'}
t1 = {'trigger': 'package_sent', 'source': 'Idle', 'target': 'Notice of package'}
t2 = {'trigger': 'package_at_pickup', 'source': 'Notice of package', 'target': 'Ready for drone pickup'}
t3 = {'trigger': 'picked_up', 'source': 'Ready for drone pickup', 'target': 'In transport'}
t4 = {'trigger': 'dropped_off', 'source': 'In transport', 'target': 'At delivery place'}
t5 = {'trigger': 'delivered', 'source': 'At delivery place', 'target': 'Idle', 'effect': 'remove_package'}
t6 = {'trigger': 't', 'source': 'At delivery place', 'target': 'Return to sender'}
t7 = {'trigger': 'returned', 'source': 'Return to sender', 'target': 'Idle', 'effect': 'remove_package'}

# Define States with Entry Actions
idle = {'name': 'Idle', 'entry': 'on_idle'}
notice = {'name': 'Notice of package', 'entry': 'on_notice'}
pickup = {'name': 'Ready for drone pickup', 'entry': 'on_pickup_ready'}
transport = {'name': 'In transport', 'entry': 'on_transport'}
at_place = {'name': 'At delivery place', 'entry': 'on_delivery_place; start_timer("t", 5000)'}
ret_sender = {'name': 'Return to sender', 'entry': 'on_return'}