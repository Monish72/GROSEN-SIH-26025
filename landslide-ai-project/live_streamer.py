import time
import random
import requests

# GROSEN: Telemetry endpoint URL for sensor packet streaming.
URL = "http://127.0.0.1:8000/api/telemetry"

# Pit sensor node inventory with baseline geotechnical coordinates.
NODES = [
    {
        "id": "NODE_01",
        "name": "Pit Floor Sump Extensometer",
        "base_pitch": 1.15,
        "base_roll": 0.45,
        "base_tilt": 1.23,
        "rssi": -63.5,
        "snr": 9.4
    },
    {
        "id": "NODE_02",
        "name": "East Highwall Escarpment",
        "base_pitch": 1.40,
        "base_roll": 0.65,
        "base_tilt": 1.54,
        "rssi": -66.0,
        "snr": 8.8
    },
    {
        "id": "NODE_03",
        "name": "West Incline Haul Road",
        "base_pitch": 0.85,
        "base_roll": 0.35,
        "base_tilt": 0.92,
        "rssi": -67.0,
        "snr": 9.1
    }
]

print("=== GROSEN: LIVE NODE STREAMER ACTIVE ===")
print("Connecting NODE_01, NODE_02, and NODE_03 to command center...")

seq = 1
# Continuous loop transmitting simulated sensor packets to backend every 2 seconds.
while True:
    for node in NODES:
        # Generate simulated sensor metrics with baseline noise and ambient vibration.
        jitter = random.uniform(-0.006, 0.006)
        vib_rms = random.uniform(0.005, 0.011)
        vib_peak = random.uniform(0.015, 0.030)
        temp = random.uniform(28.8, 29.4)
        battery = random.uniform(4.12, 4.18)

        # Build telemetry payload dictionary conforming to backend schema.
        payload = {
            "node_id": node["id"],
            "timestamp": int(time.time()),
            "power": {
                "battery_v": round(battery, 2),
                "is_charging": True
            },
            "metrics": {
                "tilt_pitch_deg": round(node["base_pitch"] + jitter, 2),
                "tilt_roll_deg": round(node["base_roll"] + jitter * 0.7, 2),
                "tilt_total_deg": round(node["base_tilt"] + jitter, 2),
                "vibration_rms_g": round(vib_rms, 4),
                "vibration_peak_g": round(vib_peak, 4),
                "temp_c": round(temp, 1)
            },
            "rf": {
                "rssi_dbm": round(node["rssi"] + random.uniform(-0.5, 0.5), 1),
                "snr_db": round(node["snr"] + random.uniform(-0.2, 0.2), 1)
            }
        }

        # Post telemetry packet to backend API over HTTP.
        try:
            r = requests.post(URL, json=payload, timeout=1.5)
        except Exception as e:
            pass

    seq += 1
    time.sleep(2.0)
