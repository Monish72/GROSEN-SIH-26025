import time
import random
import requests
import sys
import os

# GROSEN: Hardware sensor node simulator modeling Saito creep progression for pit monitoring.
URL = "http://127.0.0.1:8000/api/telemetry"
NODES = ["NODE_01", "NODE_02"]

# ANSI terminal color escape codes for CLI output formatting.
RESET   = "\033[0m"
BOLD    = "\033[1m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
RED     = "\033[31m"
CYAN    = "\033[36m"
GRAY    = "\033[90m"
WHITE   = "\033[97m"

DEMO_DURATION = 180  # 3 minutes total
TICK_INTERVAL = 2    # 2 seconds per tick

# Baseline and dynamic tilt tracking dictionary per simulated node.
node_sim_state = {
    "NODE_01": {"baseline": 1.8, "current_tilt": 1.8},
    "NODE_02": {"baseline": 2.1, "current_tilt": 2.1},
}

# Simulate progressive slope deformation across Saito creep stages over 180 seconds.
def generate_telemetry(node_id, elapsed_seconds):
    state = node_sim_state[node_id]
    
    if elapsed_seconds < 60:
        # Calculate nominal baseline parameters during stable phase (0 to 60s).
        v_target = 0.0
        vib_rms = random.uniform(0.005, 0.015)
        vib_peak = random.uniform(0.018, 0.045)
        battery = random.uniform(4.10, 4.18)
        temp = random.uniform(29.0, 30.5)

    elif elapsed_seconds < 120:
        # Accelerate target displacement velocity and vibration during secondary creep phase (60 to 120s).
        p2_progress = (elapsed_seconds - 60) / 60.0
        
        if node_id == "NODE_01":
            v_target = 0.5 + (p2_progress * 6.0)
            vib_rms = 0.035 + (0.06 * p2_progress) + random.uniform(0.0, 0.01)
            vib_peak = 0.20 + (0.35 * p2_progress) + random.uniform(0.0, 0.04)
        elif node_id == "NODE_02":
            v_target = 0.35 + (p2_progress * 2.0)
            vib_rms = 0.025 + (0.02 * p2_progress)
            vib_peak = 0.15 + (0.15 * p2_progress)
        else:
            v_target = 0.35
            vib_rms = random.uniform(0.02, 0.035)
            vib_peak = random.uniform(0.12, 0.22)

        battery = random.uniform(4.00, 4.14)
        temp = random.uniform(30.5, 32.5)

    else:
        # Trigger runaway displacement velocity and severe vibration during tertiary creep phase (120 to 180s).
        p3_progress = (elapsed_seconds - 120) / 60.0
        
        if node_id == "NODE_01":
            v_target = 6.5 + (p3_progress ** 1.3) * 18.0
            vib_rms = 0.10 + (0.25 * p3_progress) + random.uniform(0.0, 0.03)
            vib_peak = 0.60 + (1.40 * p3_progress) + random.uniform(0.0, 0.15)
        elif node_id == "NODE_02":
            v_target = 2.35 + (p3_progress * 3.0)
            vib_rms = 0.045 + (0.04 * p3_progress)
            vib_peak = 0.30 + (0.25 * p3_progress)
        else:
            v_target = 0.35
            vib_rms = random.uniform(0.02, 0.035)
            vib_peak = random.uniform(0.12, 0.22)

        battery = random.uniform(3.92, 4.08)
        temp = random.uniform(32.0, 34.5)

    # Increment integrated physical tilt position based on target velocity.
    state["current_tilt"] += (v_target / 3600.0) * TICK_INTERVAL
    
    # Inject electronic noise into raw tilt angle measurement.
    measured_tilt = state["current_tilt"] + random.uniform(-0.0015, 0.0015)

    # Model RF signal attenuation correlating with physical ground subsidence.
    if elapsed_seconds < 60:
        base_rssi = -64.0 if node_id == "NODE_01" else -65.5
        base_snr = 9.0
    elif elapsed_seconds < 120:
        p2 = (elapsed_seconds - 60) / 60.0
        base_rssi = -64.0 - (7.0 * p2) if node_id == "NODE_01" else -65.5 - (1.5 * p2)
        base_snr = 9.0 - (2.5 * p2) if node_id == "NODE_01" else 8.5
    else:
        p3 = (elapsed_seconds - 120) / 60.0
        base_rssi = -71.0 - (10.0 * p3) if node_id == "NODE_01" else -67.0 - (2.0 * p3)
        base_snr = 6.5 - (4.0 * p3) if node_id == "NODE_01" else 8.0

    # Add multipath Gaussian noise to simulated RSSI and SNR readings.
    sim_rssi = base_rssi + random.gauss(0, 0.8)
    sim_snr = max(-5.0, base_snr + random.gauss(0, 0.4))

    return {
        "node_id": node_id,
        "timestamp": int(time.time()),
        "power": {
            "battery_v": round(battery, 2),
            "is_charging": True
        },
        "metrics": {
            "tilt_pitch_deg": round(measured_tilt * 0.7, 3),
            "tilt_roll_deg": round(measured_tilt * 0.3, 3),
            "tilt_total_deg": round(measured_tilt, 3),
            "vibration_rms_g": round(vib_rms, 3),
            "vibration_peak_g": round(vib_peak, 3),
            "temp_c": round(temp, 1)
        },
        "rf": {
            "rssi_dbm": round(sim_rssi, 1),
            "snr_db": round(sim_snr, 1)
        }
    }

# Clear terminal screen and display formatted GROSEN simulator banner.
def print_header():
    os.system('cls' if os.name == 'nt' else 'clear')
    print(f"{CYAN}{BOLD}========================================================================{RESET}")
    print(f"{WHITE}{BOLD}       GROSEN - SECTOR 4 PIT REAL-TIME HARDWARE SIMULATOR              {RESET}")
    print(f"{GRAY}   Physics-Grounded 3-Minute Demo Playback Mode (Saito Creep Theory)   {RESET}")
    print(f"{CYAN}{BOLD}========================================================================{RESET}\n")

# Execute continuous 3-minute demonstration cycles simulating slope failure.
def run_demo_simulation():
    demo_cycle = 1
    
    while True:
        # Reset node continuous physical positions for clean demo cycle start.
        for nid in node_sim_state:
            node_sim_state[nid]["current_tilt"] = node_sim_state[nid]["baseline"]
            
        # Send reset request to backend to clear historical state and alarms.
        try:
            requests.post("http://127.0.0.1:8000/api/reset", timeout=2)
        except Exception:
            pass
            
        start_time = time.time()
        print_header()
        print(f"{GREEN}[INFO] Starting 3-Minute Live Playback Cycle #{demo_cycle}...{RESET}\n")

        while True:
            elapsed = time.time() - start_time
            if elapsed >= DEMO_DURATION:
                break

            # Evaluate active creep phase based on elapsed seconds.
            if elapsed < 60:
                phase_num = 1
                phase_name = "PHASE 1: STABLE BASELINE OPERATION"
                phase_color = GREEN
            elif elapsed < 120:
                phase_num = 2
                phase_name = "PHASE 2: SECONDARY ACCELERATING CREEP (WARNING)"
                phase_color = YELLOW
            else:
                phase_num = 3
                phase_name = "PHASE 3: TERTIARY RUNAWAY CREEP & SLOPE FAILURE (CRITICAL)"
                phase_color = RED

            # Render CLI progress bar, percentage, and active geotechnical phase.
            progress_pct = min(100.0, (elapsed / DEMO_DURATION) * 100)
            bar_len = 24
            filled_len = int(bar_len * elapsed // DEMO_DURATION)
            bar = '=' * filled_len + '-' * (bar_len - filled_len)
            mins = int(elapsed // 60)
            secs = int(elapsed % 60)
            time_str = f"{mins:02d}:{secs:02d} / 03:00"

            print(f"\r{BOLD}[{time_str}] [{bar}] {progress_pct:4.1f}% | {phase_color}{phase_name}{RESET}", flush=True)
            print("-" * 72)

            # Transmit telemetry packets for active sensor nodes.
            for node in NODES:
                payload = generate_telemetry(node, elapsed)
                
                try:
                    res = requests.post(URL, json=payload, timeout=2)
                    res_json = res.json()
                    risk = res_json.get("risk_score", 0.0)
                    
                    tilt = payload["metrics"]["tilt_total_deg"]
                    vib = payload["metrics"]["vibration_peak_g"]
                    
                    if risk > 0.7:
                        status_tag = f"{RED}{BOLD}CRITICAL FAIL{RESET}"
                        row_color = RED
                    elif risk > 0.4:
                        status_tag = f"{YELLOW}{BOLD}CREEP WARNING{RESET}"
                        row_color = YELLOW
                    elif res_json.get("status") == "calibrating":
                        status_tag = f"{CYAN}CALIBRATING  {RESET}"
                        row_color = CYAN
                    else:
                        status_tag = f"{GREEN}STABLE       {RESET}"
                        row_color = WHITE

                    rf_info = payload.get("rf", {})
                    rssi_val = rf_info.get("rssi_dbm", -65.0)
                    print(f" {row_color}> {node:<8}{RESET} | Status: {status_tag} | Risk: {risk*100:5.1f}% | Tilt: {tilt:5.2f} deg | RSSI: {rssi_val:5.1f}dBm")

                except requests.exceptions.ConnectionError:
                    print(f" {RED}[X] {node:<8} | Offline - Server not reachable at {URL}{RESET}")
                except Exception as ex:
                    print(f" {RED}[X] {node:<8} | Transmission Error: {ex}{RESET}")

            print("-" * 72)
            time.sleep(TICK_INTERVAL)
            # Return cursor up for clean terminal line overwriting.
            print("\033[6A", end="", flush=True)

        print("\n\n" + "=" * 72)
        print(f"{RED}{BOLD}[!] 3-MINUTE DEMO PLAYBACK COMPLETE: PIT EVACUATION SCENARIO REACHED!{RESET}")
        print(f"{GRAY}Auto-restarting in 5 seconds for continuous booth/demo presentation...{RESET}")
        print("=" * 72 + "\n")
        time.sleep(5)
        demo_cycle += 1

# Entry point to execute the hardware simulation loop.
if __name__ == "__main__":
    try:
        run_demo_simulation()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Demo simulation paused by user.{RESET}")
        sys.exit(0)