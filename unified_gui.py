import tkinter as tk
from tkinter import ttk, messagebox
import paho.mqtt.client as mqtt
import stmpy
import json
import logging
import random
import string
import time

# Import components from use cases
from usecase1.StateMachine import (
    DroneComponent,
    t0 as dt0, t1 as dt1, t2 as dt2, t3 as dt3, t4 as dt4, t5 as dt5, t6 as dt6, t7 as dt7, t8 as dt8, t9 as dt9,
    idle as d_idle, diagnostic as d_diag, ready as d_ready, charging as d_charging, maintenance as d_maint, offline as d_offline
)
from usecase2.StateMachine import (
    PackageDeliveryComponent,
    t0 as pt0, t1 as pt1, t2 as pt2, t3 as pt3, t4 as pt4, t5 as pt5, t6 as pt6, t7 as pt7,
    idle as p_idle, notice as p_notice, pickup as p_pickup, transport as p_transport, at_place as p_at_place, ret_sender as p_ret_sender
)
from usecase3.StateMachine import (
    OrderProcessComponent,
    t0 as ot0, t1 as ot1, t2 as ot2, t3 as ot3, t4 as ot4, t5 as ot5, t6 as ot6,
    idle as o_idle, confirming as o_confirming, create as o_create, finding as o_finding, preparing as o_preparing
)

# Constants
BROKER = "broker.hivemq.com"
PORT = 1883
MAX_PAYMENT_ATTEMPTS = 3

class UnifiedDroneApp:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger("UnifiedApp")

        # MQTT Client
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect(BROKER, PORT)
        self.mqtt_client.loop_start()

        # Components
        self.drone_id = "Drone-Alpha"
        self.package_id = "PKG-DEFAULT"
        
        self.drone_logic = DroneComponent(self.drone_id, self.mqtt_client)
        self.order_logic = OrderProcessComponent(self.mqtt_client)
        self.package_logic = PackageDeliveryComponent(self.package_id, self.mqtt_client)

        # Drivers & Machines
        self.driver = stmpy.Driver()
        
        self.drone_machine = stmpy.Machine(
            name="drone_stm",
            transitions=[dt0, dt1, dt2, dt3, dt4, dt5, dt6, dt7, dt8, dt9],
            obj=self.drone_logic,
            states=[d_idle, d_diag, d_ready, d_charging, d_maint, d_offline],
        )
        self.drone_logic.stm = self.drone_machine

        self.order_machine = stmpy.Machine(
            name="order_stm",
            transitions=[ot0, ot1, ot2, ot3, ot4, ot5, ot6],
            obj=self.order_logic,
            states=[o_idle, o_confirming, o_create, o_finding, o_preparing],
        )
        self.order_logic.stm = self.order_machine

        self.package_machine = stmpy.Machine(
            name='package_stm', 
            transitions=[pt0, pt1, pt2, pt3, pt4, pt5, pt6, pt7], 
            obj=self.package_logic,
            states=[p_idle, p_notice, p_pickup, p_transport, p_at_place, p_ret_sender]
        )
        self.package_logic.stm = self.package_machine

        self.driver.add_machine(self.drone_machine)
        self.driver.add_machine(self.order_machine)
        self.driver.add_machine(self.package_machine)
        self.driver.start()

        # GUI
        self.create_gui()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self.logger.info("Connected to MQTT broker.")
        self.mqtt_client.subscribe("order/status")
        self.mqtt_client.subscribe(f"drone/{self.drone_id}/status")
        self.mqtt_client.subscribe(f"delivery/+/status")

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            topic = msg.topic
            
            # Orchestration Logic
            if topic == "order/status":
                self.root.after(0, self.update_order_display, data)
                
                # If Order is FINDING_DRONE, trigger Drone Diagnostic
                if data["status"] == "FINDING_DRONE":
                    self.logger.info("Orchestrator: Order is looking for a drone. Triggering UC-1 Diagnostic.")
                    self.driver.send("run_diag", "drone_stm")
                
                # If Order is IDLE and we just finished an assignment, start delivery tracking
                if data["status"] == "IDLE" and data["message"].startswith("Order"):
                    self.logger.info("Orchestrator: Order confirmed. Triggering UC-2 Tracking.")
                    # Update package ID in logic if needed, here we just use default
                    self.driver.send("package_sent", "package_stm")

            elif topic.startswith("drone/"):
                self.root.after(0, self.update_drone_display, data)
                
                # If Drone is READY and Order is in FINDING_DRONE, notify Order
                if data["status"] == "READY":
                    # Check if order is currently finding
                    if self.order_machine.state == "Finding drone":
                        self.logger.info("Orchestrator: Drone is READY. Notifying UC-3.")
                        self.driver.send("available_drone_found", "order_stm")

            elif topic.startswith("delivery/"):
                self.root.after(0, self.update_delivery_display, data)
        except Exception as e:
            self.logger.error(f"Error processing message: {e}")

    # GUI Update Methods
    def update_order_display(self, data):
        status = data["status"]
        self.lbl_o_status.config(text=f"STATUS: {status}")
        self.lbl_o_msg.config(text=data["message"])
        order = data["order"]
        self.lbl_o_tracking.config(text=f"Tracking #: {order['tracking_number'] or '—'}")
        self.lbl_o_drone.config(text=f"Assigned: {order['assigned_drone'] or '—'}")

    def update_drone_display(self, data):
        status = data["status"]
        self.lbl_d_status.config(text=f"STATUS: {status}")
        self.lbl_d_msg.config(text=data["message"])
        t = data["telemetry"]
        self.lbl_d_battery.config(text=f"Battery: {t['battery']:.1f}%")
        self.lbl_d_checks.config(text=f"Rotor: {'OK' if t['rotor_ok'] else 'FAIL'} | Sensors: {'OK' if t['sensors_ok'] else 'FAIL'}")

    def update_delivery_display(self, data):
        status = data["status"]
        self.lbl_p_status.config(text=f"STATE: {status.upper()}")
        t = data["telemetry"]
        self.lbl_p_battery.config(text=f"Drone Battery: {t['battery']}%")
        self.lbl_p_speed.config(text=f"Speed: {t['speed']} km/h")
        self.lbl_p_eta.config(text=f"ETA: {t['eta']}")

    # User Actions
    def submit_order(self):
        name = self.ent_name.get()
        if not name:
            messagebox.showwarning("Input Error", "Please enter a sender name.")
            return
        
        self.order_logic.information(
            location={"pickup": "Facility A", "destination": "User Home"},
            measurements={"weight_kg": 2.5},
            personal_info={"name": name, "email": f"{name}@example.com"},
        )
        self.order_logic.payment()
        self.driver.send("order_sent", "order_stm")

    def confirm_payment(self):
        self.driver.send("payment_confirmed", "order_stm")

    def dispatch_drone(self):
        self.driver.send("drone_sent", "order_stm")

    def trigger_delivery_step(self, trigger):
        self.driver.send(trigger, "package_stm")

    def set_drone_scenario(self, battery, rotor_ok, sensors_ok):
        self.drone_logic.telemetry["battery"] = battery
        self.drone_logic.telemetry["rotor_ok"] = rotor_ok
        self.drone_logic.telemetry["sensors_ok"] = sensors_ok
        self.logger.info(f"Scenario set: bat={battery}, rotor={rotor_ok}, sensors={sensors_ok}")

    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("Unified Drone Delivery System (Team 14)")
        self.root.geometry("1100x700")
        
        style = ttk.Style()
        style.configure("Header.TLabel", font=("Helvetica", 12, "bold"))
        
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill="both", expand=True)

        # 3-Column Layout
        col1 = ttk.LabelFrame(main_frame, text="UC-3: Order Registration", padding=10)
        col1.pack(side="left", fill="both", expand=True, padx=5)

        col2 = ttk.LabelFrame(main_frame, text="UC-1: Drone Readiness", padding=10)
        col2.pack(side="left", fill="both", expand=True, padx=5)

        col3 = ttk.LabelFrame(main_frame, text="UC-2: Delivery Tracking", padding=10)
        col3.pack(side="left", fill="both", expand=True, padx=5)

        # --- Column 1: Order ---
        self.lbl_o_status = ttk.Label(col1, text="STATUS: IDLE", font=("Helvetica", 10, "bold"))
        self.lbl_o_status.pack(pady=5)
        self.lbl_o_msg = ttk.Label(col1, text="Waiting for new order...", wraplength=300)
        self.lbl_o_msg.pack(pady=5)
        
        ttk.Label(col1, text="Sender Name:").pack(anchor="w")
        self.ent_name = ttk.Entry(col1)
        self.ent_name.insert(0, "Marius")
        self.ent_name.pack(fill="x", pady=2)
        
        ttk.Button(col1, text="1. Submit Order", command=self.submit_order).pack(fill="x", pady=5)
        ttk.Button(col1, text="2. Confirm Payment", command=self.confirm_payment).pack(fill="x", pady=5)
        
        self.lbl_o_tracking = ttk.Label(col1, text="Tracking #: —")
        self.lbl_o_tracking.pack(pady=2)
        self.lbl_o_drone = ttk.Label(col1, text="Assigned: —")
        self.lbl_o_drone.pack(pady=2)
        
        ttk.Button(col1, text="3. Dispatch Drone", command=self.dispatch_drone).pack(fill="x", pady=10)

        # --- Column 2: Drone ---
        self.lbl_d_status = ttk.Label(col2, text="STATUS: IDLE", font=("Helvetica", 10, "bold"))
        self.lbl_d_status.pack(pady=5)
        self.lbl_d_msg = ttk.Label(col2, text="Drone standby.", wraplength=300)
        self.lbl_d_msg.pack(pady=5)
        
        self.lbl_d_battery = ttk.Label(col2, text="Battery: --")
        self.lbl_d_battery.pack()
        self.lbl_d_checks = ttk.Label(col2, text="Rotor: -- | Sensors: --")
        self.lbl_d_checks.pack()
        
        ttk.Label(col2, text="Simulate Scenarios:", font=("Helvetica", 9, "italic")).pack(pady=10)
        ttk.Button(col2, text="Healthy (100%)", command=lambda: self.set_drone_scenario(100, True, True)).pack(fill="x", pady=2)
        ttk.Button(col2, text="Low Battery (30%)", command=lambda: self.set_drone_scenario(30, True, True)).pack(fill="x", pady=2)
        ttk.Button(col2, text="Rotor Failure", command=lambda: self.set_drone_scenario(80, False, True)).pack(fill="x", pady=2)
        
        ttk.Button(col2, text="Manual Diagnostic", command=lambda: self.driver.send("run_diag", "drone_stm")).pack(fill="x", pady=20)

        # --- Column 3: Tracking ---
        self.lbl_p_status = ttk.Label(col3, text="STATE: IDLE", font=("Helvetica", 10, "bold"))
        self.lbl_p_status.pack(pady=5)
        
        self.lbl_p_battery = ttk.Label(col3, text="Drone Battery: --")
        self.lbl_p_battery.pack()
        self.lbl_p_speed = ttk.Label(col3, text="Speed: --")
        self.lbl_p_speed.pack()
        self.lbl_p_eta = ttk.Label(col3, text="ETA: --")
        self.lbl_p_eta.pack()
        
        ttk.Label(col3, text="Manual Tracking Steps:", font=("Helvetica", 9, "italic")).pack(pady=10)
        ttk.Button(col3, text="Arrived at Pickup", command=lambda: self.trigger_delivery_step("package_at_pickup")).pack(fill="x", pady=2)
        ttk.Button(col3, text="Picked Up", command=lambda: self.trigger_delivery_step("picked_up")).pack(fill="x", pady=2)
        ttk.Button(col3, text="Dropped Off", command=lambda: self.trigger_delivery_step("dropped_off")).pack(fill="x", pady=2)
        ttk.Button(col3, text="Confirm Delivered", command=lambda: self.trigger_delivery_step("delivered")).pack(fill="x", pady=2)

        # Footer
        footer = ttk.Label(main_frame, text="MQTT Broker: broker.hivemq.com | Communication: Active", foreground="gray")
        footer.pack(side="bottom", pady=10)

    def start(self):
        self.root.mainloop()

    def stop(self):
        self.driver.stop()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.root.destroy()

if __name__ == "__main__":
    app = UnifiedDroneApp()
    app.start()
