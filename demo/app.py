import tkinter as tk
from tkinter import ttk
import paho.mqtt.client as mqtt
import stmpy
import json
import logging
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from usecase1.StateMachine import DroneComponent,           UC1_TRANSITIONS, UC1_STATES
from usecase2.StateMachine import PackageDeliveryComponent, UC2_TRANSITIONS, UC2_STATES
from usecase3.StateMachine import OrderProcessComponent,    UC3_TRANSITIONS, UC3_STATES

DRONE_CONFIGS = [
    {"id": "Drone-Alpha", "battery": 85.0, "rotor_ok": True,  "sensors_ok": True,  "communication_ok": True},
    {"id": "Drone-Beta",  "battery": 35.0, "rotor_ok": True,  "sensors_ok": True,  "communication_ok": True},
    {"id": "Drone-Gamma", "battery": 72.0, "rotor_ok": False, "sensors_ok": True,  "communication_ok": True},
    {"id": "Drone-Delta", "battery": 0.0,  "rotor_ok": False, "sensors_ok": False, "communication_ok": False},
]

STATUS_COLORS = {
    "IDLE":        "grey",
    "DIAGNOSTIC":  "orange",
    "READY":       "green",
    "CHARGING":    "royalblue",
    "MAINTENANCE": "red",
    "OFFLINE":     "darkred",
    "DELIVERING":  "purple",
}

DELIVERY_COLORS = {
    "Idle":                  "grey",
    "Notice of package":     "orange",
    "Ready for drone pickup": "royalblue",
    "In transport":          "purple",
    "At delivery place":     "green",
    "Return to sender":      "red",
}

MAX_PAYMENT_ATTEMPTS = 3


class UnifiedApp:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self._logger = logging.getLogger(__name__)

        self.drone_statuses        = {}  
        self.current_delivery_drone = None

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect("broker.hivemq.com", 1883)
        self.mqtt_client.loop_start()

        self.driver = stmpy.Driver()

        self.drone_components = {}
        for cfg in DRONE_CONFIGS:
            comp = DroneComponent(
                drone_id=cfg["id"], mqtt_client=self.mqtt_client,
                battery=cfg["battery"], rotor_ok=cfg["rotor_ok"],
                sensors_ok=cfg["sensors_ok"], communication_ok=cfg["communication_ok"],
            )
            machine = stmpy.Machine(
                name=cfg["id"], transitions=UC1_TRANSITIONS,
                obj=comp, states=UC1_STATES,
            )
            comp.stm = machine
            self.drone_components[cfg["id"]] = comp
            self.driver.add_machine(machine)

        self.delivery_comp = PackageDeliveryComponent(self.mqtt_client)
        self.driver.add_machine(stmpy.Machine(
            name="delivery_stm", transitions=UC2_TRANSITIONS,
            obj=self.delivery_comp, states=UC2_STATES,
        ))

        self.order_comp = OrderProcessComponent(
            mqtt_client=self.mqtt_client,
            get_ready_drone=self.get_ready_drone,
            on_order_confirmed=self.on_order_confirmed,
        )
        order_machine = stmpy.Machine(
            name="order_stm", transitions=UC3_TRANSITIONS,
            obj=self.order_comp, states=UC3_STATES,
        )
        self.order_comp.stm = order_machine
        self.driver.add_machine(order_machine)

        self.driver.start()

        self.create_gui()

        for drone_id in self.drone_components:
            self.driver.send("run_diag", drone_id)


    def get_ready_drone(self):
        """Return the first READY drone from the live fleet, or fall back to Alpha."""
        for cfg in DRONE_CONFIGS:
            if self.drone_statuses.get(cfg["id"]) == "READY":
                return cfg["id"]
        return DRONE_CONFIGS[0]["id"]

    def on_order_confirmed(self, order):
        """Called by UC-3 when an order is confirmed — kicks off UC-2 delivery."""
        drone_id = order["assigned_drone"]
        pkg_id   = order["tracking_number"]

        self.delivery_comp.drone_id   = drone_id
        self.delivery_comp.package_id = pkg_id
        self.delivery_comp.telemetry  = {"battery": 100, "speed": 0, "eta": "Calculating..."}
        self.current_delivery_drone   = drone_id

        self.driver.send("package_sent", "delivery_stm")

        self.root.after(0, lambda: self.notebook.select(self.delivery_tab))
        self.root.after(0, lambda: self.lbl_delivery_header.config(
            text=f"Drone: {drone_id}   |   Package: {pkg_id}", fg="black"))


    def on_connect(self, client, userdata, flags, reason_code, properties):
        self._logger.info("Connected to MQTT broker.")
        self.mqtt_client.subscribe("drone/+/status")
        self.mqtt_client.subscribe("delivery/+/status")
        self.mqtt_client.subscribe("order/status")

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return
        topic = msg.topic
        if topic.startswith("drone/"):
            self.root.after(0, self.handle_drone_status, data)
        elif topic.startswith("delivery/"):
            self.root.after(0, self.handle_delivery_status, data)
        elif topic == "order/status":
            self.root.after(0, self.handle_order_status, data)

    def handle_drone_status(self, data):
        drone_id = data.get("drone_id")
        if not drone_id or drone_id not in self.fleet_widgets:
            return
        status = data["status"]
        self.drone_statuses[drone_id] = status
        t = data["telemetry"]
        w = self.fleet_widgets[drone_id]
        w["status"].config(text=status, fg=STATUS_COLORS.get(status, "black"))
        w["message"].config(text=data["message"])
        w["battery"].config(text=f"Battery: {t['battery']:.1f}%")
        w["rotor"].config(text=f"Rotor: {'OK' if t['rotor_ok'] else 'FAIL'}",
                          fg="green" if t["rotor_ok"] else "red")
        w["sensors"].config(text=f"Sensors: {'OK' if t['sensors_ok'] else 'FAIL'}",
                            fg="green" if t["sensors_ok"] else "red")
        w["comms"].config(text=f"Comms: {'OK' if t['communication_ok'] else 'FAIL'}",
                          fg="green" if t["communication_ok"] else "red")

    def handle_delivery_status(self, data):
        uc2_status = data.get("status", "")
        drone_id   = data.get("drone_id")

        self.update_delivery_display(data)

        if drone_id and drone_id in self.drone_components:
            if uc2_status == "In transport":
                self.driver.send("drone_busy", drone_id)
            elif uc2_status == "Idle" and self.current_delivery_drone == drone_id:
                self.driver.send("drone_free", drone_id)
                self.current_delivery_drone = None

    def handle_order_status(self, data):
        status = data.get("status", "")
        order  = data.get("order", {})
        colors = {
            "IDLE":               "grey",
            "CONFIRMING_PAYMENT": "orange",
            "CREATE_ORDER":       "royalblue",
            "FINDING_DRONE":      "purple",
            "PREPARING_DRONE":    "darkgreen",
        }
        self.lbl_order_status.config(
            text=f"STATUS: {status}", fg=colors.get(status, "black"))
        self.lbl_order_message.config(text=data.get("message", ""))
        self.lbl_order_tracking.config(
            text=f"Tracking #: {order.get('tracking_number') or '—'}")
        self.lbl_order_drone.config(
            text=f"Assigned drone: {order.get('assigned_drone') or '—'}")
        attempts = order.get("payment_attempts", 0)
        self.lbl_order_attempts.config(
            text=f"Payment attempts: {attempts}",
            fg="red" if attempts >= MAX_PAYMENT_ATTEMPTS else "black")

    def update_delivery_display(self, data):
        uc2_status = data.get("status", "—")
        self.lbl_delivery_status.config(
            text=f"STATE: {uc2_status.upper()}",
            fg=DELIVERY_COLORS.get(uc2_status, "black"))
        t = data.get("telemetry", {})
        self.lbl_delivery_battery.config(text=f"Battery: {t.get('battery', '--')}%")
        self.lbl_delivery_speed.config(text=f"Speed: {t.get('speed', '--')} km/h")
        self.lbl_delivery_eta.config(text=f"ETA: {t.get('eta', '--')}")


    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("Drone Delivery System — Integrated Demo")
        self.root.geometry("600x680")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        tk.Label(self.root, text="Drone Delivery System",
                 font=("Helvetica", 16, "bold")).pack(pady=8)

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=4)

        self.fleet_tab    = ttk.Frame(self.notebook)
        self.order_tab    = ttk.Frame(self.notebook)
        self.delivery_tab = ttk.Frame(self.notebook)

        self.notebook.add(self.fleet_tab,    text="  Fleet Status (UC-1)  ")
        self.notebook.add(self.order_tab,    text="  Register Order (UC-3)  ")
        self.notebook.add(self.delivery_tab, text="  Track Delivery (UC-2)  ")

        self.create_fleet_tab(self.fleet_tab)
        self.create_order_tab(self.order_tab)
        self.create_delivery_tab(self.delivery_tab)


    def create_fleet_tab(self, parent):
        self.fleet_widgets = {}

        tk.Label(parent, text="Live Fleet Status",
                 font=("Helvetica", 12, "bold")).pack(pady=6)

        for cfg in DRONE_CONFIGS:
            drone_id = cfg["id"]
            frame = tk.LabelFrame(parent, text=drone_id, font=("Helvetica", 10, "bold"))
            frame.pack(fill="x", padx=10, pady=4, ipady=3)

            top = tk.Frame(frame)
            top.pack(fill="x", padx=6)

            lbl_status  = tk.Label(top, text="IDLE", font=("Helvetica", 11, "bold"),
                                   fg="grey", width=12, anchor="w")
            lbl_battery = tk.Label(top, text="Battery: --", font=("Helvetica", 9))
            lbl_rotor   = tk.Label(top, text="Rotor: --",   font=("Helvetica", 9))
            lbl_sensors = tk.Label(top, text="Sensors: --", font=("Helvetica", 9))
            lbl_comms   = tk.Label(top, text="Comms: --",   font=("Helvetica", 9))

            for w in (lbl_status, lbl_battery, lbl_rotor, lbl_sensors, lbl_comms):
                w.pack(side="left", padx=4)

            bot = tk.Frame(frame)
            bot.pack(fill="x", padx=6, pady=2)

            lbl_message = tk.Label(bot, text="—", font=("Helvetica", 8),
                                   fg="grey", anchor="w", wraplength=500)
            lbl_message.pack(side="left", fill="x", expand=True)

            tk.Button(bot, text="Re-diagnose",
                      command=lambda did=drone_id: self.re_diagnose(did)
                      ).pack(side="right")

            self.fleet_widgets[drone_id] = {
                "status":  lbl_status,  "battery": lbl_battery,
                "rotor":   lbl_rotor,   "sensors": lbl_sensors,
                "comms":   lbl_comms,   "message": lbl_message,
            }

        tk.Button(parent, text="Re-diagnose All Drones", height=2, bg="lightblue",
                  command=self.re_diagnose_all).pack(fill="x", padx=10, pady=8)


    def create_order_tab(self, parent):
        hud = tk.LabelFrame(parent, text="Order Status", font=("Helvetica", 11, "bold"))
        hud.pack(fill="x", padx=10, pady=8, ipady=4)

        self.lbl_order_status = tk.Label(
            hud, text="STATUS: IDLE", font=("Helvetica", 12, "bold"), fg="grey")
        self.lbl_order_status.pack(pady=2)
        self.lbl_order_message = tk.Label(
            hud, text="No active order.", font=("Helvetica", 9), wraplength=520)
        self.lbl_order_message.pack()
        self.lbl_order_tracking = tk.Label(hud, text="Tracking #: —", font=("Helvetica", 9))
        self.lbl_order_tracking.pack()
        self.lbl_order_drone = tk.Label(hud, text="Assigned drone: —", font=("Helvetica", 9))
        self.lbl_order_drone.pack()
        self.lbl_order_attempts = tk.Label(hud, text="Payment attempts: 0", font=("Helvetica", 9))
        self.lbl_order_attempts.pack()

        form = tk.LabelFrame(parent, text="Step 1 — Package Details")
        form.pack(fill="x", padx=10, pady=4, ipady=3)

        for label, attr in [
            ("Sender name",    "entry_name"),
            ("Sender email",   "entry_email"),
            ("Pickup address", "entry_pickup"),
            ("Destination",    "entry_dest"),
            ("Weight (kg)",    "entry_weight"),
        ]:
            row = tk.Frame(form)
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=label, width=16, anchor="w").pack(side="left")
            entry = tk.Entry(row)
            entry.pack(side="left", fill="x", expand=True)
            setattr(self, attr, entry)

        tk.Button(form, text="Submit Order", height=2, bg="lightblue",
                  command=self.submit_order).pack(fill="x", padx=8, pady=5)

        pay = tk.LabelFrame(parent, text="Step 2 — Payment (Simulate)")
        pay.pack(fill="x", padx=10, pady=4, ipady=3)

        tk.Button(pay, text="Payment Confirmed", height=2, bg="lightgreen",
                  command=self.confirm_payment).pack(fill="x", padx=8, pady=3)
        tk.Button(pay, text="Payment Failed  (order cancelled after 3 failures)",
                  height=2, bg="#ffcccc",
                  command=self.fail_payment).pack(fill="x", padx=8, pady=3)


    def create_delivery_tab(self, parent):
        hud = tk.LabelFrame(parent, text="Live Delivery Telemetry", font=("Helvetica", 11, "bold"))
        hud.pack(fill="x", padx=10, pady=8, ipady=6)

        self.lbl_delivery_header = tk.Label(
            hud, text="No active delivery — register an order first.",
            font=("Helvetica", 10, "italic"), fg="grey")
        self.lbl_delivery_header.pack()

        self.lbl_delivery_status = tk.Label(
            hud, text="STATE: IDLE", font=("Helvetica", 13, "bold"), fg="grey")
        self.lbl_delivery_status.pack(pady=4)

        self.lbl_delivery_battery = tk.Label(hud, text="Battery: --", font=("Helvetica", 10))
        self.lbl_delivery_battery.pack()
        self.lbl_delivery_speed = tk.Label(hud, text="Speed: --", font=("Helvetica", 10))
        self.lbl_delivery_speed.pack()
        self.lbl_delivery_eta = tk.Label(hud, text="ETA: --", font=("Helvetica", 10))
        self.lbl_delivery_eta.pack()

        ctrl = tk.LabelFrame(parent, text="Delivery Controls  (simulate real-world events)")
        ctrl.pack(fill="both", expand=True, padx=10, pady=5)

        for text, trigger in [
            ("1. Arrive at pickup location",      "package_at_pickup"),
            ("2. Pick up the package",             "picked_up"),
            ("3. Drop off at destination",         "dropped_off"),
            ("4. Confirm delivery",                "delivered"),
            ("5. Package returned to sender",      "returned"),
        ]:
            tk.Button(ctrl, text=text, height=2,
                      command=lambda t=trigger: self.driver.send(t, "delivery_stm")
                      ).pack(fill="x", padx=10, pady=3)

        tk.Label(ctrl,
                 text="Note: if delivery isn't confirmed within 8 s of drop-off, "
                      "the drone automatically returns to sender.",
                 fg="grey", font=("Helvetica", 8), wraplength=520).pack(pady=4)


    def submit_order(self):
        name   = self.entry_name.get().strip()
        email  = self.entry_email.get().strip()
        pickup = self.entry_pickup.get().strip()
        dest   = self.entry_dest.get().strip()
        weight = self.entry_weight.get().strip()

        if not all([name, email, pickup, dest, weight]):
            self.lbl_order_message.config(text="Please fill in all fields.", fg="red")
            return

        self.order_comp.information(
            location={"pickup": pickup, "destination": dest},
            measurements={"weight_kg": weight},
            personal_info={"name": name, "email": email},
        )
        self.driver.send("order_sent", "order_stm")

    def confirm_payment(self):
        self.driver.send("payment_confirmed", "order_stm")

    def fail_payment(self):
        if self.order_comp.order["payment_attempts"] >= MAX_PAYMENT_ATTEMPTS:
            self.lbl_order_message.config(
                text=f"Payment failed {MAX_PAYMENT_ATTEMPTS} times. Order cancelled.", fg="red")
            self.driver.send("payment_failed", "order_stm")
        else:
            self.driver.send("payment_failed", "order_stm")
            self.driver.send("order_sent", "order_stm")

    def re_diagnose(self, drone_id):
        self.driver.send("go_idle", drone_id)
        self.driver.send("run_diag", drone_id)

    def re_diagnose_all(self):
        for drone_id in self.drone_components:
            self.re_diagnose(drone_id)

    def start(self):
        self.root.mainloop()

    def stop(self):
        self._logger.info("Shutting down...")
        self.driver.stop()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    app = UnifiedApp()
    app.start()
