import paho.mqtt.client as mqtt
import json
import threading

try:
    from sense_hat import SenseHat
    sense = SenseHat()
    HARDWARE_MODE = True
except ImportError:
    sense = None
    HARDWARE_MODE = False
    print("⚠️ sense_hat not found. Running in software-only mode.")

# UC1 - Drone diagnostics  (drone/+/status)
UC1_DISPLAY = {
    "IDLE":        ("IDLE",      (0,   0,   255)),
    "DIAGNOSTIC":  ("DIAG",      (255, 165, 0)),
    "READY":       ("READY",     (0,   200, 0)),
    "CHARGING":    ("CHARGE",    (0,   180, 255)),
    "MAINTENANCE": ("MAINT",     (255, 80,  0)),
    "OFFLINE":     ("OFFLINE",   (80,  0,   0)),
    "DELIVERING":  ("DELIVER",   (180, 0,   180)),
}

# UC2 - Package delivery  (delivery/+/status)
UC2_DISPLAY = {
    "Idle":                   ("IDLE",     (0,   0,   255)),
    "Notice of package":      ("NOTICE",   (0,   255, 255)),
    "Ready for drone pickup": ("READY",    (255, 255, 0)),
    "In transport":           ("TRANSIT",  (0,   200, 0)),
    "At delivery place":      ("ARRIVED",  (180, 0,   180)),
    "Return to sender":       ("RETURN",   (255, 0,   0)),
}

# UC3 - Order processing  (order/status)
UC3_DISPLAY = {
    "IDLE":               ("IDLE",    (0,   0,   255)),
    "CONFIRMING_PAYMENT": ("PAYMENT", (255, 200, 0)),
    "CREATE_ORDER":       ("ORDER",   (0,   255, 200)),
    "FINDING_DRONE":      ("FINDING", (0,   180, 255)),
    "PREPARING_DRONE":    ("PREP",    (180, 0,   180)),
}

SUBSCRIPTIONS = [
    ("drone/+/status",    UC1_DISPLAY),
    ("delivery/+/status", UC2_DISPLAY),
    ("order/status",      UC3_DISPLAY),
]


_display_lock = threading.Lock()
_latest_msg = [None]  # tracks the most recently requested (label, color)


def show_status(label, color):
    print(f"[DISPLAY] {label}")
    if not sense:
        return
    _latest_msg[0] = (label, color)

    def _run():
        with _display_lock:
            # If a newer message arrived while waiting for the lock, skip this one
            if _latest_msg[0] != (label, color):
                return
            sense.set_rotation(0)
            sense.show_message(label, text_colour=color, back_colour=(0, 0, 0), scroll_speed=0.06)
            sense.clear(*color)

    threading.Thread(target=_run, daemon=True).start()


def on_connect(client, userdata, flags, rc, properties=None):
    print("Connected to MQTT broker.")
    for topic, _ in SUBSCRIPTIONS:
        client.subscribe(topic)
        print(f"  Subscribed: {topic}")


def on_message(client, userdata, msg):
    try:
        data = json.loads(msg.payload.decode("utf-8"))
        status = data.get("status", "")
        topic = msg.topic

        if topic.startswith("drone/"):
            display_map = UC1_DISPLAY
        elif topic.startswith("delivery/"):
            display_map = UC2_DISPLAY
        elif topic.startswith("order/"):
            display_map = UC3_DISPLAY
        else:
            return

        label, color = display_map.get(status, ("?", (255, 255, 255)))
        show_status(label, color)

    except Exception as e:
        print(f"Failed to parse message: {e}")


client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
client.on_connect = on_connect
client.on_message = on_message
client.connect("broker.hivemq.com", 1883)

print("Pi Display running (Ctrl+C to stop)...")
try:
    client.loop_forever()
except KeyboardInterrupt:
    print("\nStopping...")
    if sense:
        sense.clear()
