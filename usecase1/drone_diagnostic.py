import tkinter as tk
import paho.mqtt.client as mqtt
import stmpy
import json
import logging

from StateMachine import DroneComponent, ALL_TRANSITIONS, ALL_STATES

# Pre-configured fleet — mirrors the UC-1 demo scenarios
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
    "CHARGING":    "blue",
    "MAINTENANCE": "red",
    "OFFLINE":     "darkred",
    "DELIVERING":  "purple",
}


class FleetDashboardApp:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self._logger = logging.getLogger(__name__)

        # MQTT
        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect("broker.hivemq.com", 1883)
        self.mqtt_client.loop_start()

        # Build one stmpy machine per drone
        self.components = {}   # drone_id → DroneComponent
        self.driver = stmpy.Driver()

        for cfg in DRONE_CONFIGS:
            comp = DroneComponent(
                drone_id=cfg["id"],
                mqtt_client=self.mqtt_client,
                battery=cfg["battery"],
                rotor_ok=cfg["rotor_ok"],
                sensors_ok=cfg["sensors_ok"],
                communication_ok=cfg["communication_ok"],
            )
            machine = stmpy.Machine(
                name=cfg["id"],
                transitions=ALL_TRANSITIONS,
                obj=comp,
                states=ALL_STATES,
            )
            comp.stm = machine
            self.components[cfg["id"]] = comp
            self.driver.add_machine(machine)

        self.driver.start()

        self.create_gui()

        # Run initial diagnostic for every drone so the dashboard shows real statuses
        for drone_id in self.components:
            self.driver.send("run_diag", drone_id)

    # ------------------------------------------------------------------
    # MQTT callbacks
    # ------------------------------------------------------------------
    def on_connect(self, client, userdata, flags, reason_code, properties):
        self._logger.info("Connected to MQTT broker.")
        # Own drone diagnostics
        self.mqtt_client.subscribe("drone/+/status")
        # UC-2 delivery events — tells us when a drone is out on a job
        self.mqtt_client.subscribe("delivery/+/status")

    def on_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            return

        topic = msg.topic
        if topic.startswith("drone/"):
            # Own diagnostic update
            self.root.after(0, self.handle_drone_status, data)
        elif topic.startswith("delivery/"):
            # UC-2 delivery update
            self.root.after(0, self.handle_delivery_status, data)

    def handle_drone_status(self, data):
        drone_id = data.get("drone_id")
        if drone_id not in self.widgets:
            return
        status = data["status"]
        t = data["telemetry"]
        w = self.widgets[drone_id]
        w["status"].config(text=status, fg=STATUS_COLORS.get(status, "black"))
        w["message"].config(text=data["message"])
        w["battery"].config(text=f"Battery: {t['battery']:.1f}%")
        w["rotor"].config(text=f"Rotor: {'OK' if t['rotor_ok'] else 'FAIL'}", fg="green" if t["rotor_ok"] else "red")
        w["sensors"].config(text=f"Sensors: {'OK' if t['sensors_ok'] else 'FAIL'}", fg="green" if t["sensors_ok"] else "red")
        w["comms"].config(text=f"Comms: {'OK' if t['communication_ok'] else 'FAIL'}", fg="green" if t["communication_ok"] else "red")

    def handle_delivery_status(self, data):
        # UC-2 publishes which drone is doing the delivery
        drone_id = data.get("drone_id")
        uc2_status = data.get("status", "")

        if not drone_id or drone_id not in self.components:
            return

        if uc2_status == "In transport":
            self.driver.send("drone_busy", drone_id)
        elif uc2_status == "Idle":
            self.driver.send("drone_free", drone_id)

    # ------------------------------------------------------------------
    # GUI
    # ------------------------------------------------------------------
    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("UC-1: Drone Fleet Dashboard")
        self.root.geometry("520x640")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        tk.Label(self.root, text="Drone Fleet Dashboard",
                 font=("Helvetica", 14, "bold")).pack(pady=8)

        self.widgets = {}

        for cfg in DRONE_CONFIGS:
            drone_id = cfg["id"]
            frame = tk.LabelFrame(self.root, text=drone_id, font=("Helvetica", 11, "bold"))
            frame.pack(fill="x", padx=12, pady=5, ipady=4)

            top = tk.Frame(frame)
            top.pack(fill="x", padx=8)

            lbl_status = tk.Label(top, text="IDLE", font=("Helvetica", 12, "bold"), fg="grey", width=14, anchor="w")
            lbl_status.pack(side="left")

            lbl_battery = tk.Label(top, text="Battery: --", font=("Helvetica", 10))
            lbl_battery.pack(side="left", padx=8)

            lbl_rotor = tk.Label(top, text="Rotor: --", font=("Helvetica", 10))
            lbl_rotor.pack(side="left", padx=4)

            lbl_sensors = tk.Label(top, text="Sensors: --", font=("Helvetica", 10))
            lbl_sensors.pack(side="left", padx=4)

            lbl_comms = tk.Label(top, text="Comms: --", font=("Helvetica", 10))
            lbl_comms.pack(side="left", padx=4)

            bottom = tk.Frame(frame)
            bottom.pack(fill="x", padx=8, pady=2)

            lbl_message = tk.Label(bottom, text="—", font=("Helvetica", 9), fg="grey", anchor="w", wraplength=460)
            lbl_message.pack(side="left", fill="x", expand=True)

            tk.Button(bottom, text="Re-diagnose",
                      command=lambda did=drone_id: self.run_diagnostic(did)
                      ).pack(side="right")

            self.widgets[drone_id] = {
                "status":  lbl_status,
                "battery": lbl_battery,
                "rotor":   lbl_rotor,
                "sensors": lbl_sensors,
                "comms":   lbl_comms,
                "message": lbl_message,
            }

        tk.Button(self.root, text="Re-diagnose All Drones", height=2, bg="lightblue",
                  command=self.run_all_diagnostics).pack(fill="x", padx=12, pady=10)

    def run_diagnostic(self, drone_id):
        # Reset to idle first, then trigger diagnostic
        self.driver.send("go_idle", drone_id)
        self.driver.send("run_diag", drone_id)

    def run_all_diagnostics(self):
        for drone_id in self.components:
            self.run_diagnostic(drone_id)

    def start(self):
        self.root.mainloop()

    def stop(self):
        self._logger.info("Shutting down fleet dashboard...")
        self.driver.stop()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    app = FleetDashboardApp()
    app.start()
