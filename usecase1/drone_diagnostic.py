import tkinter as tk
import paho.mqtt.client as mqtt
import stmpy
import json
import logging

from StateMachine import (
    DroneComponent,
    t0, t1, t2, t3, t4, t5, t6, t7, t8, t9,
    idle, diagnostic, ready, charging, maintenance, offline,
)


class DroneMonitorApp:
    def __init__(self):
        logging.basicConfig(level=logging.INFO)
        self._logger = logging.getLogger(__name__)
        self.drone_id = "Drone-Alpha"
        self.topic = f"drone/{self.drone_id}/status"

        self.mqtt_client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        self.mqtt_client.on_connect = self.on_connect
        self.mqtt_client.on_message = self.on_message
        self.mqtt_client.connect("broker.hivemq.com", 1883)
        self.mqtt_client.loop_start()

        self.drone = DroneComponent(self.drone_id, self.mqtt_client)
        self.machine = stmpy.Machine(
            name="drone_stm",
            transitions=[t0, t1, t2, t3, t4, t5, t6, t7, t8, t9],
            obj=self.drone,
            states=[idle, diagnostic, ready, charging, maintenance, offline],
        )
        self.drone.stm = self.machine
        self.driver = stmpy.Driver()
        self.driver.add_machine(self.machine)
        self.driver.start()

        self.create_gui()

    def on_connect(self, client, userdata, flags, reason_code, properties):
        self._logger.info("Connected to MQTT broker.")
        self.mqtt_client.subscribe(self.topic)

    def on_message(self, client, userdata, msg):
        data = json.loads(msg.payload.decode("utf-8"))
        self.root.after(0, self.update_display, data)

    def update_display(self, data):
        status = data["status"]
        colors = {
            "IDLE": "grey",
            "DIAGNOSTIC": "orange",
            "READY": "green",
            "CHARGING": "blue",
            "MAINTENANCE": "red",
            "OFFLINE": "darkred",
        }
        color = colors.get(status, "black")
        self.lbl_status.config(text=f"STATUS: {status}", fg=color)
        self.lbl_message.config(text=data["message"])
        t = data["telemetry"]
        self.lbl_battery.config(text=f"Battery: {t['battery']:.1f}%")
        self.lbl_rotor.config(text=f"Rotor OK: {t['rotor_ok']}")
        self.lbl_sensors.config(text=f"Sensors OK: {t['sensors_ok']}")
        self.lbl_comms.config(text=f"Comms OK: {t['communication_ok']}")

    def run_diagnostic(self):
        self.driver.send("run_diag", "drone_stm")

    def reset_drone(self):
        self.driver.send("go_idle", "drone_stm")

    def set_scenario(self, battery, rotor_ok, sensors_ok, comms_ok):
        self.drone.telemetry["battery"] = battery
        self.drone.telemetry["rotor_ok"] = rotor_ok
        self.drone.telemetry["sensors_ok"] = sensors_ok
        self.drone.telemetry["communication_ok"] = comms_ok
        self._logger.info(f"Scenario set: battery={battery}, rotor={rotor_ok}, sensors={sensors_ok}, comms={comms_ok}")

    def create_gui(self):
        self.root = tk.Tk()
        self.root.title("Drone Diagnostic Monitor")
        self.root.geometry("380x560")
        self.root.protocol("WM_DELETE_WINDOW", self.stop)

        hud = tk.LabelFrame(self.root, text="Live Drone Status", font=("Helvetica", 12, "bold"))
        hud.pack(fill="x", padx=10, pady=10, ipady=8)

        self.lbl_status = tk.Label(hud, text="STATUS: IDLE", font=("Helvetica", 14, "bold"), fg="grey")
        self.lbl_status.pack(pady=4)

        self.lbl_message = tk.Label(hud, text="Drone idle. Awaiting diagnostic.", font=("Helvetica", 10), wraplength=340)
        self.lbl_message.pack()

        self.lbl_battery  = tk.Label(hud, text="Battery: --",    font=("Helvetica", 10))
        self.lbl_rotor    = tk.Label(hud, text="Rotor OK: --",   font=("Helvetica", 10))
        self.lbl_sensors  = tk.Label(hud, text="Sensors OK: --", font=("Helvetica", 10))
        self.lbl_comms    = tk.Label(hud, text="Comms OK: --",   font=("Helvetica", 10))
        for lbl in (self.lbl_battery, self.lbl_rotor, self.lbl_sensors, self.lbl_comms):
            lbl.pack()

        sc = tk.LabelFrame(self.root, text="Simulate Drone Scenario")
        sc.pack(fill="x", padx=10, pady=5, ipady=4)

        def btn(parent, text, **kwargs):
            tk.Button(parent, text=text, height=2, command=lambda: self.set_scenario(**kwargs)).pack(fill="x", padx=8, pady=3)

        btn(sc, "Healthy (READY)",             battery=85.0, rotor_ok=True,  sensors_ok=True,  comms_ok=True)
        btn(sc, "Low Battery (CHARGING)",      battery=35.0, rotor_ok=True,  sensors_ok=True,  comms_ok=True)
        btn(sc, "Rotor Failure (MAINTENANCE)", battery=75.0, rotor_ok=False, sensors_ok=True,  comms_ok=True)
        btn(sc, "No Comms (OFFLINE)",          battery=80.0, rotor_ok=True,  sensors_ok=True,  comms_ok=False)

        ctrl = tk.LabelFrame(self.root, text="Controls")
        ctrl.pack(fill="x", padx=10, pady=5, ipady=4)

        tk.Button(ctrl, text="Run Diagnostic", height=2, bg="lightblue",
                  command=self.run_diagnostic).pack(fill="x", padx=8, pady=3)
        tk.Button(ctrl, text="Reset to Idle", height=2,
                  command=self.reset_drone).pack(fill="x", padx=8, pady=3)

    def start(self):
        self.root.mainloop()

    def stop(self):
        self._logger.info("Shutting down...")
        self.driver.stop()
        self.mqtt_client.loop_stop()
        self.mqtt_client.disconnect()
        self.root.destroy()


if __name__ == "__main__":
    app = DroneMonitorApp()
    app.start()
