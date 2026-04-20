import tkinter as tk
import paho.mqtt.client as mqtt
import stmpy
import json
import time
import logging


ASSIGNED_DRONE = "Drone-Alpha"  # Which UC-1 fleet drone is doing this delivery


class PackageDeliveryComponent:
    def __init__(self, package_id, mqtt_client):
        self.package_id = package_id
        self.mqtt_client = mqtt_client
        self.topic = f"delivery/{package_id}/status"

        self.telemetry = {
            "pos": [63.4305, 10.3951], # Trondheim coordinates
            "battery": 100,
            "speed": 0,
            "eta": "Calculating..."
        }

    def _publish_update(self, state_name):
        payload = {
            "package_id": self.package_id,
            "drone_id": ASSIGNED_DRONE,  # UC-1 fleet dashboard listens for this
            "status": state_name,
            "telemetry": self.telemetry,
            "timestamp": time.time()
        }
        self.mqtt_client.publish(self.topic, json.dumps(payload))

    def on_idle(self):
        self.telemetry["speed"] = 0
        self._publish_update("Idle")

    def on_notice(self):
        self._publish_update("Notice of package")
        
    def on_pickup_ready(self):
        self._publish_update("Ready for drone pickup")

    def on_transport(self):
        self.telemetry["speed"] = 45 # km/h
        self.telemetry["battery"] -= 5
        self.telemetry["eta"] = "12 mins"
        self._publish_update("In transport")

    def on_delivery_place(self):
        self.telemetry["speed"] = 0
        self.telemetry["eta"] = "Arrived"
        self._publish_update("At delivery place")

    def on_return(self):
        self.telemetry["speed"] = 45
        self.telemetry["eta"] = "Returning..."
        self._publish_update("Return to sender")

    def remove_package(self):
        print(f"[{self.package_id}] Cleaned up resources.")


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
at_place = {'name': 'At delivery place', 'entry': 'on_delivery_place; start_timer("t", 8000)'} # 8 second timer
ret_sender = {'name': 'Return to sender', 'entry': 'on_return'}

class DroneHUDApp:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self._logger = logging.getLogger(__name__)
        self.package_id = "PKG-123"
        self.topic = f"delivery/{self.package_id}/status"

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect("broker.hivemq.com", 1883)
        self.mqtt_client.loop_start()

        self.delivery_logic = PackageDeliveryComponent(self.package_id, self.mqtt_client)
        self.machine = stmpy.Machine(
            name='package_stm', 
            transitions=[t0, t1, t2, t3, t4, t5, t6, t7], 
            obj=self.delivery_logic,
            states=[idle, notice, pickup, transport, at_place, ret_sender]
        )
        self.driver = stmpy.Driver()
        self.driver.add_machine(self.machine)
        self.driver.start()

        self.create_gui()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self._logger.info(f'Connected to MQTT broker.')
        self.mqtt_client.subscribe(self.topic)

    def on_message(self, client, userdata, msg):
        """Receives MQTT JSON and updates the GUI HUD safely."""
        payload_str = msg.payload.decode('utf-8')
        data = json.loads(payload_str)

        self.root.after(0, self.update_hud_display, data)

    def update_hud_display(self, data):
        """Formats the JSON data into the HUD labels."""
        self.lbl_status.config(text=f"STATE: {data['status'].upper()}", fg="blue")
        self.lbl_battery.config(text=f"Battery: {data['telemetry']['battery']}%")
        self.lbl_speed.config(text=f"Speed: {data['telemetry']['speed']} km/h")
        self.lbl_eta.config(text=f"ETA: {data['telemetry']['eta']}")

    def send_trigger(self, trigger_name):
        """Sends a trigger to the STMPY state machine."""
        self._logger.info(f"Sending trigger: {trigger_name}")
        self.driver.send(trigger_name, 'package_stm')

    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("Drone Delivery HUD")
        self.root.geometry("350x550")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        hud_frame = tk.LabelFrame(self.root, text="Live Telemetry HUD", font=('Helvetica', 12, 'bold'))
        hud_frame.pack(fill="x", padx=10, pady=10, ipady=10)

        self.lbl_status = tk.Label(hud_frame, text="STATE: WAITING...", font=('Helvetica', 14, 'bold'))
        self.lbl_status.pack(pady=5)

        self.lbl_battery = tk.Label(hud_frame, text="Battery: --", font=('Helvetica', 11))
        self.lbl_battery.pack()

        self.lbl_speed = tk.Label(hud_frame, text="Speed: --", font=('Helvetica', 11))
        self.lbl_speed.pack()

        self.lbl_eta = tk.Label(hud_frame, text="ETA: --", font=('Helvetica', 11))
        self.lbl_eta.pack()

        ctrl_frame = tk.LabelFrame(self.root, text="System Controls (Send Triggers)")
        ctrl_frame.pack(fill="both", expand=True, padx=10, pady=5)

        def add_btn(parent, text, trigger):
            tk.Button(parent, text=text, height=2, command=lambda: self.send_trigger(trigger)).pack(fill="x", padx=10, pady=5)

        add_btn(ctrl_frame, "1. Send Package (package_sent)", "package_sent")
        add_btn(ctrl_frame, "2. Arrive at Pickup (package_at_pickup)", "package_at_pickup")
        add_btn(ctrl_frame, "3. Pick Up (picked_up)", "picked_up")
        add_btn(ctrl_frame, "4. Drop Off (dropped_off)", "dropped_off")
        add_btn(ctrl_frame, "5. Confirm Delivery (delivered)", "delivered")
        add_btn(ctrl_frame, "6. Package Returned (returned)", "returned")

        tk.Label(ctrl_frame, text="Note: If 'Delivered' isn't clicked within 8\nseconds of Drop Off, drone returns to sender.", fg="grey", font=("Helvetica", 8)).pack(pady=5)

    def start(self):
        self.root.mainloop()

    def stop(self):
        self._logger.info("Stopping System...")
        self.driver.stop()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    app = DroneHUDApp()
    app.start()