import tkinter as tk
from tkinter import ttk
import paho.mqtt.client as mqtt
import stmpy
import json
import logging

from StateMachine import (
    OrderProcessComponent,
    t0, t1, t2, t3, t4, t5, t6,
    idle, confirming, create, finding, preparing,
)

MAX_PAYMENT_ATTEMPTS = 3


class OrderRegistrationApp:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self._logger = logging.getLogger(__name__)

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect("broker.hivemq.com", 1883)
        self.mqtt_client.loop_start()

        self.order_logic = OrderProcessComponent(self.mqtt_client)
        self.machine = stmpy.Machine(
            name="order_stm",
            transitions=[t0, t1, t2, t3, t4, t5, t6],
            obj=self.order_logic,
            states=[idle, confirming, create, finding, preparing],
        )
        self.order_logic.stm = self.machine
        self.driver = stmpy.Driver()
        self.driver.add_machine(self.machine)
        self.driver.start()

        self.create_gui()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self._logger.info("Connected to MQTT broker.")
        self.mqtt_client.subscribe("order/status")

    def on_message(self, client, userdata, msg):
        data = json.loads(msg.payload.decode("utf-8"))
        self.root.after(0, self.update_display, data)

    def update_display(self, data):
        status = data["status"]
        colors = {
            "IDLE":               "grey",
            "CONFIRMING_PAYMENT": "orange",
            "CREATE_ORDER":       "blue",
            "FINDING_DRONE":      "purple",
            "PREPARING_DRONE":    "darkgreen",
        }
        self.lbl_status.config(text=f"STATUS: {status}", fg=colors.get(status, "black"))
        self.lbl_message.config(text=data["message"])
        order = data["order"]
        self.lbl_tracking.config(text=f"Tracking #: {order['tracking_number'] or '—'}")
        self.lbl_drone.config(text=f"Assigned drone: {order['assigned_drone'] or '—'}")
        attempts = order["payment_attempts"]
        self.lbl_attempts.config(text=f"Payment attempts: {attempts}")
        if attempts >= MAX_PAYMENT_ATTEMPTS:
            self.lbl_attempts.config(fg="red")
        else:
            self.lbl_attempts.config(fg="black")

    def submit_order(self):
        name    = self.entry_name.get().strip()
        email   = self.entry_email.get().strip()
        pickup  = self.entry_pickup.get().strip()
        dest    = self.entry_dest.get().strip()
        weight  = self.entry_weight.get().strip()

        if not all([name, email, pickup, dest, weight]):
            self.lbl_message.config(text="Please fill in all fields.", fg="red")
            return

        self.order_logic.information(
            location={"pickup": pickup, "destination": dest},
            measurements={"weight_kg": weight},
            personal_info={"name": name, "email": email},
        )
        self.order_logic.payment()
        self.driver.send("order_sent", "order_stm")

    def confirm_payment(self):
        self.driver.send("payment_confirmed", "order_stm")

    def fail_payment(self):
        attempts = self.order_logic.order["payment_attempts"]
        if attempts >= MAX_PAYMENT_ATTEMPTS:
            self.lbl_message.config(
                text=f"Payment failed {MAX_PAYMENT_ATTEMPTS} times. Order cancelled.", fg="red"
            )
            self.driver.send("payment_failed", "order_stm")
        else:
            self.driver.send("payment_failed", "order_stm")
            self.driver.send("order_sent", "order_stm")

    def drone_found(self):
        self.driver.send("available_drone_found", "order_stm")

    def dispatch_drone(self):
        self.driver.send("drone_sent", "order_stm")

    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("UC-3: Register a Packet")
        self.root.geometry("420x660")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        hud = tk.LabelFrame(self.root, text="Order Status", font=("Helvetica", 12, "bold"))
        hud.pack(fill="x", padx=10, pady=8, ipady=6)

        self.lbl_status = tk.Label(hud, text="STATUS: IDLE", font=("Helvetica", 13, "bold"), fg="grey")
        self.lbl_status.pack(pady=3)
        self.lbl_message = tk.Label(hud, text="No active order. Awaiting new registration.",
                                    font=("Helvetica", 9), wraplength=380)
        self.lbl_message.pack()
        self.lbl_tracking = tk.Label(hud, text="Tracking #: —", font=("Helvetica", 10))
        self.lbl_tracking.pack()
        self.lbl_drone = tk.Label(hud, text="Assigned drone: —", font=("Helvetica", 10))
        self.lbl_drone.pack()
        self.lbl_attempts = tk.Label(hud, text="Payment attempts: 0", font=("Helvetica", 10))
        self.lbl_attempts.pack()

        form = tk.LabelFrame(self.root, text="Step 1 — Package Details")
        form.pack(fill="x", padx=10, pady=5, ipady=4)

        fields = [
            ("Sender name",       "entry_name"),
            ("Sender email",      "entry_email"),
            ("Pickup address",    "entry_pickup"),
            ("Destination address","entry_dest"),
            ("Weight (kg)",       "entry_weight"),
        ]
        for label, attr in fields:
            row = tk.Frame(form)
            row.pack(fill="x", padx=8, pady=2)
            tk.Label(row, text=label, width=20, anchor="w").pack(side="left")
            entry = tk.Entry(row)
            entry.pack(side="left", fill="x", expand=True)
            setattr(self, attr, entry)

        tk.Button(form, text="Submit Order", height=2, bg="lightblue",
                  command=self.submit_order).pack(fill="x", padx=8, pady=6)

        pay = tk.LabelFrame(self.root, text="Step 2 — Payment (Simulate)")
        pay.pack(fill="x", padx=10, pady=5, ipady=4)

        tk.Button(pay, text="Payment Confirmed", height=2, bg="lightgreen",
                  command=self.confirm_payment).pack(fill="x", padx=8, pady=3)
        tk.Button(pay, text="Payment Failed (retry / cancel after 3x)", height=2, bg="#ffcccc",
                  command=self.fail_payment).pack(fill="x", padx=8, pady=3)

        drone = tk.LabelFrame(self.root, text="Step 3 — Drone Assignment (Simulate)")
        drone.pack(fill="x", padx=10, pady=5, ipady=4)

        tk.Button(drone, text="Drone Found", height=2,
                  command=self.drone_found).pack(fill="x", padx=8, pady=3)
        tk.Button(drone, text="Drone Dispatched → Send Confirmation", height=2, bg="lightgreen",
                  command=self.dispatch_drone).pack(fill="x", padx=8, pady=3)

    def start(self):
        self.root.mainloop()

    def stop(self):
        self._logger.info("Shutting down...")
        self.driver.stop()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    app = OrderRegistrationApp()
    app.start()
