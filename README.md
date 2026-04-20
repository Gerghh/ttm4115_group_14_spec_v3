# Drone Delivery System — Demo

## Install dependencies

```bash
pip install paho-mqtt stmpy
```

## Run

```bash
cd demo
python app.py
```

## What you will see

The app opens with three tabs:

- **Fleet Status (UC-1)** — live status of all four drones (Alpha, Beta, Gamma, Delta), auto-diagnosed on startup. Use the re-diagnose buttons to refresh.
- **Register Order (UC-3)** — fill in package details and simulate payment. On confirmation the system automatically selects the first available drone.
- **Track Delivery (UC-2)** — step through the delivery flow. The app switches to this tab automatically when an order is confirmed.

## How the tabs connect

1. Submit an order in **Register Order** and confirm the payment.
2. The system picks the first READY drone, assigns a tracking number, and starts the delivery — the app switches to **Track Delivery**.
3. Click through the delivery steps (arrive at pickup → pick up → drop off → confirm delivery).
4. While the drone is in transport, **Fleet Status** shows it as **DELIVERING**.
5. Once the delivery is complete the drone returns to **READY** in the fleet view.
