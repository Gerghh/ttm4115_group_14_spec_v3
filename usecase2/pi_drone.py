import paho.mqtt.client as mqtt
import stmpy
import json
import time
import logging

try:
    from gpiozero import RGBLED
    HARDWARE_MODE = True
except ImportError:
    HARDWARE_MODE = False
    print("⚠️ gpiozero not found. Running in software-only mode.")

class PackageDeliveryComponent:
    def __init__(self, package_id, mqtt_client, led):
        self.package_id = package_id
        self.mqtt_client = mqtt_client
        self.led = led
        self.status_topic = f"delivery/{package_id}/status"

        self.telemetry = {"pos": [63.43, 10.39], "battery": 100, "speed": 0, "eta": "Ready"}

    def _publish_update(self, state_name, led_color=None):
        payload = {
            "package_id": self.package_id,
            "status": state_name,
            "telemetry": self.telemetry,
            "timestamp": time.time()
        }
        self.mqtt_client.publish(self.status_topic, json.dumps(payload))
        print(f"[{state_name}] Published to PC.")

        if self.led and led_color:
            self.led.color = led_color

    def on_idle(self):
        self.telemetry["speed"] = 0
        self._publish_update("Idle", (0, 0, 1))

    def on_notice(self):
        self._publish_update("Notice of package", (0, 1, 1))

    def on_pickup_ready(self):
        self._publish_update("Ready for drone pickup", (1, 1, 0))

    def on_transport(self):
        self.telemetry["speed"] = 45
        self.telemetry["battery"] -= 5
        self.telemetry["eta"] = "12 mins"
        self._publish_update("In transport", (0, 1, 0))

    def on_delivery_place(self):
        self.telemetry["speed"] = 0
        self.telemetry["eta"] = "Arrived"
        self._publish_update("At delivery place", (1, 0, 1))

    def on_return(self):
        self.telemetry["speed"] = 45
        self.telemetry["eta"] = "Returning..."
        self._publish_update("Return to sender", (1, 0, 0))

    def remove_package(self):
        print("Cleaned up resources.")

t0 = {'source': 'initial', 'target': 'Idle'}
t1 = {'trigger': 'package_sent', 'source': 'Idle', 'target': 'Notice of package'}
t2 = {'trigger': 'package_at_pickup', 'source': 'Notice of package', 'target': 'Ready for drone pickup'}
t3 = {'trigger': 'picked_up', 'source': 'Ready for drone pickup', 'target': 'In transport'}
t4 = {'trigger': 'dropped_off', 'source': 'In transport', 'target': 'At delivery place'}
t5 = {'trigger': 'delivered', 'source': 'At delivery place', 'target': 'Idle', 'effect': 'remove_package'}
t6 = {'trigger': 't', 'source': 'At delivery place', 'target': 'Return to sender'}
t7 = {'trigger': 'returned', 'source': 'Return to sender', 'target': 'Idle', 'effect': 'remove_package'}

idle = {'name': 'Idle', 'entry': 'on_idle'}
notice = {'name': 'Notice of package', 'entry': 'on_notice'}
pickup = {'name': 'Ready for drone pickup', 'entry': 'on_pickup_ready'}
transport = {'name': 'In transport', 'entry': 'on_transport'}
at_place = {'name': 'At delivery place', 'entry': 'on_delivery_place; start_timer("t", 8000)'}
ret_sender = {'name': 'Return to sender', 'entry': 'on_return'}


class PiDroneNode:
    def __init__(self):
        self.package_id = "PKG-123"
        self.command_topic = f"delivery/{self.package_id}/command"

        self.led = RGBLED(red=17, green=27, blue=22) if HARDWARE_MODE else None

        self.mqtt_client = mqtt.Client()
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect("broker.hivemq.com", 1883)
        self.mqtt_client.loop_start()

        self.delivery_logic = PackageDeliveryComponent(self.package_id, self.mqtt_client, self.led)
        self.machine = stmpy.Machine(
            name='package_stm',
            transitions=[t0, t1, t2, t3, t4, t5, t6, t7],
            obj=self.delivery_logic,
            states=[idle, notice, pickup, transport, at_place, ret_sender]
        )
        self.driver = stmpy.Driver()
        self.driver.add_machine(self.machine)
        self.driver.start()

    def on_connect(self, client, userdata, flags, rc):
        print('Pi Connected to MQTT. Waiting for commands from PC...')
        self.mqtt_client.subscribe(self.command_topic)

    def on_message(self, client, userdata, msg):
        trigger = msg.payload.decode('utf-8')
        print(f"Received command from PC: {trigger}")
        self.driver.send(trigger, 'package_stm')

    def run(self):
        print("Drone Node Running (Press Ctrl+C to stop)...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Drone Node...")
            if self.led: self.led.off()
            self.driver.stop()
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()

if __name__ == "__main__":
    node = PiDroneNode()
    node.run()
