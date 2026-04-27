# Drone Delivery System — TTM4115 Group 14

A prototype drone delivery system built with MQTT and state machines (stmpy). The system covers three use cases: drone fleet diagnostics, package delivery tracking, and order registration.

---

## Dependencies

```bash
pip install paho-mqtt stmpy
```

For Raspberry Pi hardware display:

```bash
pip install sense-hat
```

---

## Project structure

```
demo/                  — Unified PC demo app (all three use cases)
usecase1/              — UC1: Drone fleet diagnostics
usecase2/              — UC2: Package delivery tracking
usecase3/              — UC3: Order registration and processing
```

---

## Running the demo

### PC (full demo)

```bash
cd demo
python app.py
```

### PC HUD with Raspberry Pi display

Run on the PC:

```bash
cd usecase2
python pc_hud.py
```

Run on the Raspberry Pi (requires SenseHAT):

```bash
python new_pi_drone.py
```

Both devices only need an internet connection — they communicate through the public HiveMQ MQTT broker automatically.

---

## Use cases

### UC1 — Drone Fleet Diagnostics

Manages the status of a drone through diagnostics, deployment, and fault handling.

**States:** Idle → Diagnostic → Ready / Charging / Maintenance / Broken / Offline / Delivering

| Button | Effect |
|---|---|
| Run Diagnostic | Runs a 3-second diagnostic, then transitions to the appropriate result state |
| Low Battery (10%) | Sets battery to 10% and moves drone to Charging (auto-returns to Ready after 3s) |
| Drone Broken | Moves drone to Broken state |
| Send to Maintenance | Moves broken drone to Maintenance (auto-returns to Ready after 3s) |
| Drone Busy / Free | Toggles between Ready and Delivering |
| Reset to Idle | Returns drone to Idle from most states |

**MQTT topic:** `drone/{drone_id}/status`

---

### UC2 — Package Delivery Tracking

Tracks a package through its full delivery lifecycle.

**States:** Idle → Notice of package → Ready for drone pickup → In transport → At delivery place → Return to sender → Idle

| Button | Effect |
|---|---|
| Send Package | Notifies system a package is ready |
| Arrive at Pickup | Package arrives at the pickup point |
| Pick Up | Drone picks up the package |
| Drop Off | Drone drops off the package |
| Confirm Delivery | Delivery confirmed — resets to Idle |
| Package Returned | Package returned to sender — resets to Idle |

If delivery is not confirmed within 8 seconds of drop-off, the drone automatically returns the package to the sender.

**MQTT topic:** `delivery/{package_id}/status`

---

### UC3 — Order Registration

Handles the full order flow from placement to drone dispatch.

**States:** No order → Confirming payment → Create order → Finding drone → Preparing drone → No order

| Button | Effect |
|---|---|
| Place Order | Submits order details and initiates payment |
| Payment Confirmed | Confirms payment, creates order, then finds a drone after 3s |
| Payment Failed | Cancels the order and returns to idle |
| Drone Found | Assigns a drone and begins preparation |
| Drone Dispatched | Sends dispatch confirmation and resets to idle |

**MQTT topic:** `order/status`

---

## Raspberry Pi display

`new_pi_drone.py` subscribes to all three MQTT topics and displays status updates on a SenseHAT LED matrix. Each state has a unique label and colour. A 3-second cooldown prevents back-to-back updates from overlapping on the display.

| Usecase | Example states shown |
|---|---|
| UC1 | IDLE, DIAG, READY, CHARGE, MAINT, BROKEN |
| UC2 | IDLE, NOTICE, READY, TRANSIT, ARRIVED, RETURN |
| UC3 | IDLE, PAYMENT, ORDER, FINDING, PREP |
