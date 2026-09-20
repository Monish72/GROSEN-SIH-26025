# GROSEN: Standalone ESP32 gateway simulator streaming synthetic LoRa telemetry to backend.

import time
import math
import random
import requests
import sys
import os

# Backend server endpoint and timing parameters.
SERVER_URL = "http://127.0.0.1:8000/api/telemetry"
TICK_INTERVAL = 2  # seconds between transmissions
DEMO_DURATION = 180  # 3 minutes

# ANSI terminal color escape codes for CLI formatting.
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
CYAN = "\033[36m"
GRAY = "\033[90m"
WHITE = "\033[97m"

# Simulate MPU6050 accelerometer readings across stable, secondary, and tertiary creep phases.
def simulate_mpu6050_accel(node_id, elapsed):
    if elapsed < 60:
        # Phase 1: Compute nominal baseline tilt, vibration, and temperature.
        base_tilt = 1.8 if node_id == "NODE_01" else 2.1
        tilt_total = base_tilt + random.uniform(-0.01, 0.01)
        vib_rms = random.uniform(0.02, 0.035)
        vib_peak = random.uniform(0.12, 0.22)
        temp = random.uniform(29.5, 31.0)

    elif elapsed < 120:
        # Phase 2: Compute accelerating creep tilt progression and elevated vibration.
        progress = (elapsed - 60) / 60.0

        if node_id == "NODE_01":
            base_tilt = 1.8 + progress * 3.5
            vib_rms = 0.035 + (0.06 * progress)
            vib_peak = 0.20 + (0.35 * progress)
        else:
            base_tilt = 2.1 + progress * 0.5
            vib_rms = random.uniform(0.025, 0.04)
            vib_peak = random.uniform(0.15, 0.25)

        tilt_total = base_tilt + random.uniform(-0.005, 0.005)
        temp = random.uniform(30.5, 32.5)

    else:
        # Phase 3: Compute tertiary runaway tilt acceleration and severe vibration.
        progress = (elapsed - 120) / 60.0

        if node_id == "NODE_01":
            base_tilt = 5.3 + (progress ** 1.3) * 8.0
            vib_rms = 0.10 + (0.25 * progress)
            vib_peak = 0.60 + (1.40 * progress)
        else:
            base_tilt = 2.6 + progress * 1.5
            vib_rms = 0.045 + (0.04 * progress)
            vib_peak = 0.30 + (0.25 * progress)

        tilt_total = base_tilt + random.uniform(-0.005, 0.005)
        temp = random.uniform(32.0, 34.5)

    # Partition total tilt into simulated pitch and roll components.
    tilt_pitch = tilt_total * 0.7
    tilt_roll = tilt_total * 0.3

    return {
        "tilt_pitch_deg": round(tilt_pitch, 3),
        "tilt_roll_deg": round(tilt_roll, 3),
        "tilt_total_deg": round(tilt_total, 3),
        "vibration_rms_g": round(vib_rms, 4),
        "vibration_peak_g": round(vib_peak, 4),
        "temp_c": round(temp, 1)
    }

# Assemble telemetry packet dictionary conforming to TelemetryPacket schema.
def build_telemetry_packet(node_id, metrics, elapsed=0.0):
    # Compute RF signal attenuation and Gaussian noise based on ground subsidence.
    if elapsed < 60:
        base_rssi = -64.0 if node_id == "NODE_01" else -65.5
        base_snr = 9.0
    elif elapsed < 120:
        p2 = (elapsed - 60) / 60.0
        base_rssi = -64.0 - (7.0 * p2) if node_id == "NODE_01" else -65.5 - (1.5 * p2)
        base_snr = 9.0 - (2.5 * p2) if node_id == "NODE_01" else 8.5
    else:
        p3 = (elapsed - 120) / 60.0
        base_rssi = -71.0 - (10.0 * p3) if node_id == "NODE_01" else -67.0 - (2.0 * p3)
        base_snr = 6.5 - (4.0 * p3) if node_id == "NODE_01" else 8.0

    sim_rssi = base_rssi + random.gauss(0, 0.8)
    sim_snr = max(-5.0, base_snr + random.gauss(0, 0.4))

    return {
        "node_id": node_id,
        "timestamp": int(time.time()),
        "power": {
            "battery_v": round(random.uniform(4.05, 4.15), 2),
            "is_charging": True
        },
        "metrics": metrics,
        "rf": {
            "rssi_dbm": round(sim_rssi, 1),
            "snr_db": round(sim_snr, 1)
        }
    }

# Execute continuous 3-minute demonstration playback cycles for simulated nodes.
def run_simulation():
    cycle = 1

    while True:
        # Reset backend state for fresh demonstration cycle.
        try:
            requests.post("http://127.0.0.1:8000/api/reset", timeout=2)
        except Exception:
            pass

        os.system('cls' if os.name == 'nt' else 'clear')
        print(f"{CYAN}{BOLD}================================================================{RESET}")
        print(f"{WHITE}{BOLD}       GROSEN - ESP32 GATEWAY HARDWARE SIMULATOR                {RESET}")
        print(f"{GRAY}   Simulating 2 LoRa Sensor Nodes -> Gateway -> Backend POST    {RESET}")
        print(f"{CYAN}{BOLD}================================================================{RESET}\n")
        print(f"{GREEN}[INFO] Starting 3-Minute Demo Cycle #{cycle}...{RESET}\n")

        start = time.time()

        while True:
            elapsed = time.time() - start
            if elapsed >= DEMO_DURATION:
                break

            # Determine active creep phase indicator string and color.
            if elapsed < 60:
                phase = f"{GREEN}PHASE 1: STABLE BASELINE{RESET}"
            elif elapsed < 120:
                phase = f"{YELLOW}PHASE 2: ACCELERATING CREEP{RESET}"
            else:
                phase = f"{RED}PHASE 3: TERTIARY FAILURE{RESET}"

            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            print(f"\r[{mins:02d}:{secs:02d}/03:00] {phase}", flush=True)
            print("-" * 60)

            # Generate and transmit telemetry packets for both nodes.
            for nid in ["NODE_01", "NODE_02"]:
                metrics = simulate_mpu6050_accel(nid, elapsed)
                payload = build_telemetry_packet(nid, metrics, elapsed)

                try:
                    res = requests.post(SERVER_URL, json=payload, timeout=3)
                    res_json = res.json()
                    risk = res_json.get("risk_score", 0.0)

                    if risk > 0.7:
                        tag = f"{RED}{BOLD}CRITICAL{RESET}"
                    elif risk > 0.4:
                        tag = f"{YELLOW}{BOLD}WARNING {RESET}"
                    elif res_json.get("status") == "calibrating":
                        tag = f"{CYAN}CALIB   {RESET}"
                    else:
                        tag = f"{GREEN}STABLE  {RESET}"

                    tilt = metrics["tilt_total_deg"]
                    vib = metrics["vibration_peak_g"]
                    print(f"  > {nid} | {tag} | Risk: {risk*100:5.1f}% | Tilt: {tilt:5.2f} deg | Vib: {vib:4.2f}g")

                except requests.exceptions.ConnectionError:
                    print(f"  {RED}x {nid} | Server offline at {SERVER_URL}{RESET}")
                except Exception as ex:
                    print(f"  {RED}x {nid} | Error: {ex}{RESET}")

            print("-" * 60)
            time.sleep(TICK_INTERVAL)
            # Return cursor up for clean terminal refresh.
            print("\033[7A", end="", flush=True)

        print("\n\n" + "=" * 60)
        print(f"{RED}{BOLD}! 3-MINUTE DEMO COMPLETE{RESET}")
        print(f"{GRAY}Restarting in 5 seconds...{RESET}")
        print("=" * 60 + "\n")
        time.sleep(5)
        cycle += 1

# Entry point to execute the simulator loop.
if __name__ == "__main__":
    try:
        run_simulation()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Simulation stopped.{RESET}")
        sys.exit(0)
