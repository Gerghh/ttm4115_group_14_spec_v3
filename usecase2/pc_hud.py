import tkinter as tk
from tkinter import ttk
import paho.mqtt.client as mqtt
import stmpy
import json
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from usecase1.StateMachine import DroneComponent,           ALL_TRANSITIONS, ALL_STATES
from usecase2.StateMachine import PackageDeliveryComponent, UC2_TRANSITIONS, UC2_STATES
from usecase3.StateMachine import OrderProcessComponent,    UC3_TRANSITIONS, UC3_STATES

UC1_COLORS = {
    "IDLE": "grey", "DIAGNOSTIC": "orange", "READY": "green",
    "CHARGING": "royalblue", "MAINTENANCE": "darkorange",
    "BROKEN": "red", "OFFLINE": "darkred", "DELIVERING": "purple",
}
UC2_COLORS = {
    "Idle": "grey", "Notice of package": "orange",
    "Ready for drone pickup": "royalblue", "In transport": "purple",
    "At delivery place": "green", "Return to sender": "red",
}
UC3_COLORS = {
    "IDLE": "grey", "CONFIRMING_PAYMENT": "orange", "CREATE_ORDER": "teal",
    "FINDING_DRONE": "royalblue", "PREPARING_DRONE": "purple",
}


class PcHudApp:
    def __init__(self):
        logging.basicConfig(level=logging.WARNING)
        self._logger = logging.getLogger(__name__)

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect("broker.hivemq.com", 1883)
        self.mqtt_client.loop_start()

        self.uc2_current_state = None

        self.driver = stmpy.Driver()
        self._setup_uc1()
        self._setup_uc2()
        self._setup_uc3()
        self.driver.start()

        self._build_gui()

    def on_connect(self, client, userdata, flags, rc, properties=None):
        self.mqtt_client.subscribe("drone/+/status")
        self.mqtt_client.subscribe("delivery/+/status")
        self.mqtt_client.subscribe("order/status")

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            topic = msg.topic
            if topic.startswith("drone/"):
                self.root.after(0, self._update_uc1, data)
            elif topic.startswith("delivery/"):
                self.root.after(0, self._update_uc2, data)
            elif topic.startswith("order/"):
                self.root.after(0, self._update_uc3, data)
        except Exception:
            pass

    def _setup_uc1(self):
        self.uc1_drone = DroneComponent("DEMO-01", self.mqtt_client)
        machine = stmpy.Machine(
            name="uc1_stm",
            transitions=ALL_TRANSITIONS,
            obj=self.uc1_drone,
            states=ALL_STATES,
        )
        self.uc1_drone.stm = machine
        self.driver.add_machine(machine)

    def _setup_uc2(self):
        self.uc2_pkg = PackageDeliveryComponent("PKG-123", self.mqtt_client)
        machine = stmpy.Machine(
            name="uc2_stm",
            transitions=UC2_TRANSITIONS,
            obj=self.uc2_pkg,
            states=UC2_STATES,
        )
        self.uc2_pkg.stm = machine
        self.driver.add_machine(machine)

    def _setup_uc3(self):
        self.uc3_order = OrderProcessComponent(self.mqtt_client)
        machine = stmpy.Machine(
            name="uc3_stm",
            transitions=UC3_TRANSITIONS,
            obj=self.uc3_order,
            states=UC3_STATES,
        )
        self.uc3_order.stm = machine
        self.driver.add_machine(machine)

    def _update_uc1(self, data):
        s = data.get("status", "?")
        self.uc1_lbl_status.config(text=f"STATE: {s}", fg=UC1_COLORS.get(s, "black"))
        t = data.get("telemetry", {})
        self.uc1_lbl_battery.config(text=f"Battery: {t.get('battery', '--')}%")
        self.uc1_lbl_rotors.config(text=f"Rotors OK: {t.get('rotor_ok', '--')}")
        self.uc1_lbl_sensors.config(text=f"Sensors OK: {t.get('sensors_ok', '--')}")

    def _update_uc2(self, data):
        s = data.get("status", "?")
        self.uc2_current_state = s
        self.uc2_lbl_status.config(text=f"STATE: {s.upper()}", fg=UC2_COLORS.get(s, "black"))
        t = data.get("telemetry", {})
        self.uc2_lbl_battery.config(text=f"Battery: {t.get('battery', '--')}%")
        self.uc2_lbl_speed.config(text=f"Speed: {t.get('speed', '--')} km/h")
        self.uc2_lbl_eta.config(text=f"ETA: {t.get('eta', '--')}")

    def _update_uc3(self, data):
        s = data.get("status", "?")
        self.uc3_lbl_status.config(text=f"STATE: {s}", fg=UC3_COLORS.get(s, "black"))
        order = data.get("order", {})
        self.uc3_lbl_tracking.config(text=f"Tracking: {order.get('tracking_number') or '--'}")
        self.uc3_lbl_drone.config(text=f"Drone: {order.get('assigned_drone') or '--'}")

    def _uc2_publish_idle(self):
        import json, time
        payload = json.dumps({"package_id": "PKG-123", "status": "Idle",
                              "telemetry": {"battery": 100, "speed": 0, "eta": "Ready"},
                              "timestamp": time.time()})
        self.mqtt_client.publish("delivery/PKG-123/status", payload)

    def _uc2_confirm_delivery(self):
        if self.uc2_current_state == "At delivery place":
            self.uc2_lbl_status.config(text="STATE: IDLE", fg=UC2_COLORS["Idle"])
            self.uc2_lbl_battery.config(text="Battery: --")
            self.uc2_lbl_speed.config(text="Speed: --")
            self.uc2_lbl_eta.config(text="ETA: --")
            self._uc2_publish_idle()

    def _uc2_package_returned(self):
        if self.uc2_current_state == "Return to sender":
            self.uc2_lbl_status.config(text="STATE: IDLE", fg=UC2_COLORS["Idle"])
            self.uc2_lbl_battery.config(text="Battery: --")
            self.uc2_lbl_speed.config(text="Speed: --")
            self.uc2_lbl_eta.config(text="ETA: --")
            self._uc2_publish_idle()

    def _build_gui(self):
        self.root = tk.Tk()
        self.root.title("PC Mission Control HUD")
        self.root.geometry("400x560")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        nb.add(self._build_uc1_tab(nb), text="UC1 — Drone Diagnostics")
        nb.add(self._build_uc2_tab(nb), text="UC2 — Delivery")
        nb.add(self._build_uc3_tab(nb), text="UC3 — Order")

    def _btn(self, parent, text, cmd):
        tk.Button(parent, text=text, height=2, command=cmd).pack(fill="x", padx=10, pady=3)

    def _send(self, trigger, machine):
        self.driver.send(trigger, machine)

    def _build_uc1_tab(self, parent):
        frame = tk.Frame(parent)

        info = tk.LabelFrame(frame, text="Drone: DEMO-01", font=("Helvetica", 11, "bold"))
        info.pack(fill="x", padx=8, pady=8, ipady=6)
        self.uc1_lbl_status  = tk.Label(info, text="STATE: WAITING...", font=("Helvetica", 13, "bold"), fg="grey")
        self.uc1_lbl_status.pack(pady=4)
        self.uc1_lbl_battery = tk.Label(info, text="Battery: --", font=("Helvetica", 10))
        self.uc1_lbl_battery.pack()
        self.uc1_lbl_rotors  = tk.Label(info, text="Rotors OK: --", font=("Helvetica", 10))
        self.uc1_lbl_rotors.pack()
        self.uc1_lbl_sensors = tk.Label(info, text="Sensors OK: --", font=("Helvetica", 10))
        self.uc1_lbl_sensors.pack()

        ctrl = tk.LabelFrame(frame, text="Controls")
        ctrl.pack(fill="both", expand=True, padx=8, pady=4)
        self._btn(ctrl, "Run Diagnostic",      lambda: self._send("run_diag",            "uc1_stm"))
        self._btn(ctrl, "Reset to Idle",       lambda: self._send("go_idle",             "uc1_stm"))
        self._btn(ctrl, "Drone Busy",          lambda: self._send("drone_busy",          "uc1_stm"))
        self._btn(ctrl, "Drone Free",          lambda: self._send("drone_free",          "uc1_stm"))
        self._btn(ctrl, "Low Battery (10%)",   lambda: self._send("low_battery",         "uc1_stm"))
        self._btn(ctrl, "Drone Broken",        lambda: self._send("drone_broken",        "uc1_stm"))
        self._btn(ctrl, "Send to Maintenance", lambda: self._send("send_to_maintenance", "uc1_stm"))
        return frame

    def _build_uc2_tab(self, parent):
        frame = tk.Frame(parent)

        info = tk.LabelFrame(frame, text="Package: PKG-123", font=("Helvetica", 11, "bold"))
        info.pack(fill="x", padx=8, pady=8, ipady=6)
        self.uc2_lbl_status  = tk.Label(info, text="STATE: WAITING...", font=("Helvetica", 13, "bold"), fg="grey")
        self.uc2_lbl_status.pack(pady=4)
        self.uc2_lbl_battery = tk.Label(info, text="Battery: --", font=("Helvetica", 10))
        self.uc2_lbl_battery.pack()
        self.uc2_lbl_speed   = tk.Label(info, text="Speed: --", font=("Helvetica", 10))
        self.uc2_lbl_speed.pack()
        self.uc2_lbl_eta     = tk.Label(info, text="ETA: --", font=("Helvetica", 10))
        self.uc2_lbl_eta.pack()

        ctrl = tk.LabelFrame(frame, text="Controls")
        ctrl.pack(fill="both", expand=True, padx=8, pady=4)
        self._btn(ctrl, "1. Send Package",       lambda: self._send("package_sent",      "uc2_stm"))
        self._btn(ctrl, "2. Arrive at Pickup",   lambda: self._send("package_at_pickup", "uc2_stm"))
        self._btn(ctrl, "3. Pick Up",            lambda: self._send("picked_up",         "uc2_stm"))
        self._btn(ctrl, "4. Drop Off",           lambda: self._send("dropped_off",       "uc2_stm"))
        self._btn(ctrl, "5. Confirm Delivery",   lambda: (self._send("delivered", "uc2_stm"), self._uc2_confirm_delivery()))
        self._btn(ctrl, "6. Package Returned",   lambda: (self._send("returned",  "uc2_stm"), self._uc2_package_returned()))
        tk.Label(ctrl, text="Note: if Delivered not clicked within 8s\nof Drop Off, drone returns to sender.",
                 fg="grey", font=("Helvetica", 8)).pack(pady=4)
        return frame

    def _build_uc3_tab(self, parent):
        frame = tk.Frame(parent)

        info = tk.LabelFrame(frame, text="Order Status", font=("Helvetica", 11, "bold"))
        info.pack(fill="x", padx=8, pady=8, ipady=6)
        self.uc3_lbl_status   = tk.Label(info, text="STATE: WAITING...", font=("Helvetica", 13, "bold"), fg="grey")
        self.uc3_lbl_status.pack(pady=4)
        self.uc3_lbl_tracking = tk.Label(info, text="Tracking: --", font=("Helvetica", 10))
        self.uc3_lbl_tracking.pack()
        self.uc3_lbl_drone    = tk.Label(info, text="Drone: --", font=("Helvetica", 10))
        self.uc3_lbl_drone.pack()

        ctrl = tk.LabelFrame(frame, text="Controls")
        ctrl.pack(fill="both", expand=True, padx=8, pady=4)
        self._btn(ctrl, "1. Place Order",          lambda: self._uc3_place_order())
        self._btn(ctrl, "2. Payment Confirmed",    lambda: self._send("payment_confirmed",    "uc3_stm"))
        self._btn(ctrl, "3. Payment Failed",       lambda: self._send("payment_failed",       "uc3_stm"))
        self._btn(ctrl, "4. Drone Found",          lambda: self._send("available_drone_found","uc3_stm"))
        self._btn(ctrl, "5. Drone Dispatched",     lambda: self._send("drone_sent",           "uc3_stm"))
        return frame

    def _uc3_place_order(self):
        self.uc3_order.information(
            location={"pickup": "Trondheim Central", "dropoff": "Moholt"},
            measurements={"weight": 1.2, "size": "small"},
            personal_info={"name": "Demo User", "email": "demo@example.com"},
        )
        self._send("order_sent", "uc3_stm")

    def start(self):
        self.root.mainloop()

    def stop(self):
        self.driver.stop()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    app = PcHudApp()
    app.start()
