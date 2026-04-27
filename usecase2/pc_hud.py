import tkinter as tk
import paho.mqtt.client as mqtt
import json
import logging

class DroneHUDApp:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self._logger = logging.getLogger(__name__)
        self.package_id = "PKG-123"
        
        # We listen to status, but we SEND commands
        self.status_topic = f"delivery/{self.package_id}/status"
        self.command_topic = f"delivery/{self.package_id}/command"

        # 1. Setup MQTT
        self.mqtt_client = mqtt.Client() # Removed VERSION2 for compatibility
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect("broker.hivemq.com", 1883)
        self.mqtt_client.loop_start()

        # 2. Create GUI
        self.create_gui()

    def on_connect(self, client, userdata, flags, rc):
        self._logger.info('Connected to MQTT broker. Listening for drone data...')
        self.mqtt_client.subscribe(self.status_topic)

    def on_message(self, client, userdata, msg):
        """Receives status from the Pi and updates the HUD."""
        payload_str = msg.payload.decode('utf-8')
        data = json.loads(payload_str)
        self.root.after(0, self.update_hud_display, data)

    def update_hud_display(self, data):
        """Updates the screen."""
        self.lbl_status.config(text=f"STATE: {data['status'].upper()}", fg="blue")
        self.lbl_battery.config(text=f"Battery: {data['telemetry']['battery']}%")
        self.lbl_speed.config(text=f"Speed: {data['telemetry']['speed']} km/h")
        self.lbl_eta.config(text=f"ETA: {data['telemetry']['eta']}")

    def send_command(self, trigger_name):
        """Sends a command to the Pi to change states."""
        self._logger.info(f"Sending command to Pi: {trigger_name}")
        self.mqtt_client.publish(self.command_topic, trigger_name)

    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("Drone Mission Control")
        self.root.geometry("350x550")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        hud_frame = tk.LabelFrame(self.root, text="Live Telemetry from Pi", font=('Helvetica', 12, 'bold'))
        hud_frame.pack(fill="x", padx=10, pady=10, ipady=10)

        self.lbl_status = tk.Label(hud_frame, text="STATE: WAITING FOR PI...", font=('Helvetica', 14, 'bold'), fg="red")
        self.lbl_status.pack(pady=5)
        self.lbl_battery = tk.Label(hud_frame, text="Battery: --", font=('Helvetica', 11))
        self.lbl_battery.pack()
        self.lbl_speed = tk.Label(hud_frame, text="Speed: --", font=('Helvetica', 11))
        self.lbl_speed.pack()
        self.lbl_eta = tk.Label(hud_frame, text="ETA: --", font=('Helvetica', 11))
        self.lbl_eta.pack()

        ctrl_frame = tk.LabelFrame(self.root, text="Send Commands to Pi")
        ctrl_frame.pack(fill="both", expand=True, padx=10, pady=5)

        def add_btn(parent, text, trigger):
            tk.Button(parent, text=text, height=2, command=lambda: self.send_command(trigger)).pack(fill="x", padx=10, pady=5)

        add_btn(ctrl_frame, "1. Send Package", "package_sent")
        add_btn(ctrl_frame, "2. Arrive at Pickup", "package_at_pickup")
        add_btn(ctrl_frame, "3. Pick Up", "picked_up")
        add_btn(ctrl_frame, "4. Drop Off", "dropped_off")
        add_btn(ctrl_frame, "5. Confirm Delivery", "delivered")
        add_btn(ctrl_frame, "6. Package Returned", "returned")

    def start(self):
        self.root.mainloop()

    def stop(self):
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    app = DroneHUDApp()
    app.start()