"""
UC-1: Monitor drone availability/readiness
-------------------------------------------
Run:  python main.py

Starts 3 Pi agent simulators in the background, then opens the GUI.

Flow (matches UC-1 normal flow):
  1. GUI acts as the Drone Assignation Server / Fleet Manager
  2. "Request Drone Assignment" checks each drone in the selected facility
  3. For each candidate, it calls the drone's Pi agent → gets battery/rotors/sensors
  4. First drone that passes all checks is marked AVAILABLE and assigned
  5. Failed drones are marked CHARGING / MAINTENANCE / OFFLINE
"""

import tkinter as tk
from tkinter import ttk
import sqlite3
import httpx
import threading
import subprocess
import sys
import os
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH      = os.path.join(os.path.dirname(__file__), "fleet.db")
BATTERY_MIN  = 20.0   # minimum battery % required for delivery
AGENT_TIMEOUT = 5.0   # seconds before a drone is marked OFFLINE

DRONES = [
    # name,          facility,     agent_url,                  battery, rotors, sensors
    ("Drone-Alpha", "Facility-A", "http://localhost:8001",    85.0,    True,   True),
    ("Drone-Beta",  "Facility-A", "http://localhost:8002",    15.0,    True,   True),
    ("Drone-Gamma", "Facility-A", "http://localhost:8003",    78.0,    False,  True),
    ("Drone-Delta", "Facility-B", "http://localhost:8004",    90.0,    True,   True),
]

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def init_db():
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS drones (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT, facility TEXT, agent_url TEXT,
                status      TEXT DEFAULT 'OFFLINE',
                battery     REAL DEFAULT 0,
                rotors_ok   INTEGER DEFAULT 0,
                sensors_ok  INTEGER DEFAULT 0,
                last_checked TEXT
            )
        """)
        if db.execute("SELECT COUNT(*) FROM drones").fetchone()[0] == 0:
            db.executemany(
                "INSERT INTO drones(name,facility,agent_url) VALUES(?,?,?)",
                [(d[0], d[1], d[2]) for d in DRONES],
            )


def get_all_drones():
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        return [dict(r) for r in db.execute("SELECT * FROM drones ORDER BY id")]


def get_drone(drone_id):
    with sqlite3.connect(DB_PATH) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT * FROM drones WHERE id=?", (drone_id,)).fetchone()
        return dict(row) if row else None


def save_status(drone_id, status, battery, rotors_ok, sensors_ok):
    now = datetime.now(timezone.utc).strftime("%H:%M:%S")
    with sqlite3.connect(DB_PATH) as db:
        db.execute(
            "UPDATE drones SET status=?,battery=?,rotors_ok=?,sensors_ok=?,last_checked=? WHERE id=?",
            (status, battery, int(rotors_ok), int(sensors_ok), now, drone_id),
        )

# ---------------------------------------------------------------------------
# Business rules (UC-1 state decision)
# ---------------------------------------------------------------------------

def evaluate(battery, rotors_ok, sensors_ok, reachable):
    """Return (status, reason) based on diagnostic data."""
    if not reachable:
        return "OFFLINE",     "Drone did not respond — unreachable."
    if battery < BATTERY_MIN:
        return "CHARGING",    f"Battery {battery:.1f}% is below the required {BATTERY_MIN:.0f}%."
    if not rotors_ok:
        return "MAINTENANCE", "Rotor check failed — needs maintenance."
    if not sensors_ok:
        return "MAINTENANCE", "Sensor check failed — needs maintenance."
    return "AVAILABLE",       "All checks passed — drone is ready."


def run_diagnostic(drone_id):
    """Call the drone's Pi agent and return (status, reason, battery, rotors_ok, sensors_ok)."""
    drone = get_drone(drone_id)
    battery, rotors_ok, sensors_ok, reachable = 0.0, False, False, False
    try:
        with httpx.Client(timeout=AGENT_TIMEOUT) as client:
            resp = client.post(f"{drone['agent_url']}/diagnostic")
            resp.raise_for_status()
            data       = resp.json()
            battery    = float(data["battery_percent"])
            rotors_ok  = bool(data["rotors_ok"])
            sensors_ok = bool(data["sensors_ok"])
            reachable  = True
    except Exception:
        pass  # reachable stays False → OFFLINE

    status, reason = evaluate(battery, rotors_ok, sensors_ok, reachable)
    save_status(drone_id, status, battery, rotors_ok, sensors_ok)
    return status, reason, battery, rotors_ok, sensors_ok

# ---------------------------------------------------------------------------
# Start Pi agent simulators (background processes)
# ---------------------------------------------------------------------------

_agent_procs = []

def start_agents():
    """Launch one Pi agent per drone in DRONES list (background processes)."""
    agent_script = os.path.join(os.path.dirname(__file__), "pi_agent", "main.py")
    if not os.path.exists(agent_script):
        return
    for _, _, url, battery, rotors, sensors in DRONES:
        port = url.split(":")[-1]
        env = {
            **os.environ,
            "PORT":       port,
            "BATTERY":    str(battery),
            "ROTORS_OK":  str(rotors).lower(),
            "SENSORS_OK": str(sensors).lower(),
        }
        proc = subprocess.Popen(
            [sys.executable, agent_script],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        _agent_procs.append(proc)


def stop_agents():
    for p in _agent_procs:
        p.terminate()

# ---------------------------------------------------------------------------
# Tkinter GUI
# ---------------------------------------------------------------------------

def _darken(hex_color):
    """Return a slightly darker version of a hex color for hover effect."""
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r, g, b = max(0, r - 30), max(0, g - 30), max(0, b - 30)
    return f"#{r:02x}{g:02x}{b:02x}"

class DroneFleetApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Drone Fleet Monitor — UC-1")
        self.root.geometry("720x520")
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        init_db()
        self._build_gui()
        self._refresh_table()
        # Auto-check all drones on startup, then every 30 seconds
        self.root.after(1500, self._auto_check_all)  # short delay so agents have time to start

    # ------------------------------------------------------------------
    # GUI layout
    # ------------------------------------------------------------------

    @staticmethod
    def _btn(parent, text, command, bg, fg="white", font=("Helvetica", 10)):
        """Frame+Label button — reliably shows custom colors on macOS."""
        f = tk.Frame(parent, bg=bg, padx=10, pady=5, cursor="hand2")
        lbl = tk.Label(f, text=text, bg=bg, fg=fg, font=font)
        lbl.pack()
        for w in (f, lbl):
            w.bind("<Button-1>", lambda e: command())
            w.bind("<Enter>",    lambda e, b=bg: e.widget.master.config(bg=_darken(b)) or e.widget.config(bg=_darken(b)))
            w.bind("<Leave>",    lambda e, b=bg: e.widget.master.config(bg=b) or e.widget.config(bg=b))
        return f

    def _build_gui(self):
        # Title bar
        title = tk.Frame(self.root, bg="#1a1a2e", pady=10)
        title.pack(fill="x")
        tk.Label(title, text="Drone Fleet Monitor",
                 font=("Helvetica", 16, "bold"), bg="#1a1a2e", fg="white").pack()
        tk.Label(title, text="UC-1 · Monitor drone availability/readiness",
                 font=("Helvetica", 9), bg="#1a1a2e", fg="#888888").pack()

        # Controls row
        ctrl = tk.Frame(self.root, pady=8, padx=12)
        ctrl.pack(fill="x")

        tk.Label(ctrl, text="Facility:", font=("Helvetica", 10)).pack(side="left")
        self.facility_var = tk.StringVar(value="Facility-A")
        ttk.Combobox(ctrl, textvariable=self.facility_var,
                     values=["Facility-A", "Facility-B"],
                     width=12, state="readonly").pack(side="left", padx=(4, 12))

        self._btn(ctrl, "Request Drone Assignment", self._request_assignment,
                  bg="#2563eb", font=("Helvetica", 10, "bold")).pack(side="left", padx=4)
        self._btn(ctrl, "Check Selected", self._check_selected,
                  bg="#4b5563").pack(side="left", padx=4)
        self._btn(ctrl, "Refresh", self._refresh_table,
                  bg="#374151").pack(side="left", padx=4)

        # Fleet table
        table_frame = tk.Frame(self.root)
        table_frame.pack(fill="both", expand=True, padx=12, pady=(0, 4))

        cols = ("name", "facility", "status", "battery", "rotors", "sensors", "checked")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=9)

        for col, label, width in [
            ("name",     "Name",         140),
            ("facility", "Facility",      90),
            ("status",   "Status",       115),
            ("battery",  "Battery",       75),
            ("rotors",   "Rotors",        70),
            ("sensors",  "Sensors",       70),
            ("checked",  "Last Checked", 110),
        ]:
            self.tree.heading(col, text=label)
            self.tree.column(col, width=width, anchor="center")

        self.tree.tag_configure("AVAILABLE",   background="#1a3d1a", foreground="#86efac")
        self.tree.tag_configure("CHARGING",    background="#1a2d4a", foreground="#93c5fd")
        self.tree.tag_configure("MAINTENANCE", background="#3d2d0a", foreground="#fcd34d")
        self.tree.tag_configure("OFFLINE",     background="#2a2a2a", foreground="#9ca3af")

        sb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        # Result log
        log_frame = tk.LabelFrame(self.root, text="Result", padx=8, pady=4)
        log_frame.pack(fill="x", padx=12, pady=(0, 10))

        self.log = tk.Text(log_frame, height=5, state="disabled",
                           font=("Courier", 9), bg="#111827", fg="#d1d5db",
                           relief="flat", wrap="word")
        self.log.pack(fill="x")

    # ------------------------------------------------------------------
    # Table refresh
    # ------------------------------------------------------------------

    def _refresh_table(self):
        for row in self.tree.get_children():
            self.tree.delete(row)
        for d in get_all_drones():
            status  = d["status"] or "OFFLINE"
            checked = d["last_checked"] or "—"
            battery = f"{d['battery']:.1f}%" if d["last_checked"] else "—"
            rotors  = ("OK" if d["rotors_ok"] else "FAIL") if d["last_checked"] else "—"
            sensors = ("OK" if d["sensors_ok"] else "FAIL") if d["last_checked"] else "—"
            self.tree.insert("", "end", iid=str(d["id"]), tags=(status,),
                             values=(d["name"], d["facility"], status,
                                     battery, rotors, sensors, checked))

    # ------------------------------------------------------------------
    # Log helper
    # ------------------------------------------------------------------

    def _auto_check_all(self):
        """Check every drone in the background, then schedule the next run."""
        threading.Thread(target=self._do_check_all, daemon=True).start()
        self.root.after(30_000, self._auto_check_all)  # repeat every 30 s

    def _do_check_all(self):
        for drone in get_all_drones():
            run_diagnostic(drone["id"])
        self.root.after(0, self._refresh_table)

    def _log(self, text, color="#d1d5db"):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.insert("end", text)
        self.log.configure(state="disabled", fg=color)

    # ------------------------------------------------------------------
    # Check one drone
    # ------------------------------------------------------------------

    def _check_selected(self):
        sel = self.tree.selection()
        if not sel:
            self._log("Select a drone from the table first.", "#f59e0b")
            return
        drone_id = int(sel[0])
        name = get_drone(drone_id)["name"]
        self._log(f"Checking {name}…", "#94a3b8")
        threading.Thread(target=self._do_check, args=(drone_id,), daemon=True).start()

    def _do_check(self, drone_id):
        status, reason, *_ = run_diagnostic(drone_id)
        name  = get_drone(drone_id)["name"]
        color = {"AVAILABLE": "#86efac", "CHARGING": "#93c5fd",
                 "MAINTENANCE": "#fcd34d", "OFFLINE": "#9ca3af"}.get(status, "#d1d5db")
        self.root.after(0, self._log, f"{name}: {status}\n{reason}", color)
        self.root.after(0, self._refresh_table)

    # ------------------------------------------------------------------
    # Request drone assignment (main UC-1 flow)
    # ------------------------------------------------------------------

    def _request_assignment(self):
        facility = self.facility_var.get()
        self._log(f"Requesting drone from {facility}…", "#94a3b8")
        threading.Thread(target=self._do_assign, args=(facility,), daemon=True).start()

    def _do_assign(self, facility):
        candidates = [d for d in get_all_drones() if d["facility"] == facility]
        if not candidates:
            self.root.after(0, self._log,
                            f"No drones registered for {facility}.", "#f59e0b")
            return

        tried    = []
        assigned = None

        for drone in candidates:
            status, reason, *_ = run_diagnostic(drone["id"])
            tried.append(f"  • {drone['name']}: {status} — {reason}")
            if status == "AVAILABLE":
                assigned = drone
                break   # first available drone wins

        self.root.after(0, self._refresh_table)

        checked_text = "\n".join(tried)
        if assigned:
            text  = f"✅  Assigned: {assigned['name']}\n\nDrones checked:\n{checked_text}"
            color = "#86efac"
        else:
            text  = f"❌  No drones available in {facility}.\n\nDrones checked:\n{checked_text}"
            color = "#fca5a5"

        self.root.after(0, self._log, text, color)

    # ------------------------------------------------------------------

    def _on_close(self):
        stop_agents()
        self.root.destroy()

    def start(self):
        self.root.mainloop()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    start_agents()          # launch Pi agent simulators in background
    app = DroneFleetApp()
    app.start()
