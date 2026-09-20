import os
import sys
import json
import pickle
import time
import math
import asyncio
from typing import Optional
import numpy as np

# Anchor process working directory and system import path to script folder.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if os.getcwd() != BASE_DIR:
    os.chdir(BASE_DIR)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
try:
    import serial
    import serial.tools.list_ports
except ImportError:
    serial = None
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from filterpy.kalman import KalmanFilter

app = FastAPI(title="GROSEN - Mine Subsidence & Landslide AI Command Center")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load node network topology definitions and trained machine learning model.
with open("topology.json", "r") as f:
    TOPOLOGY = json.load(f)

with open("model.pkl", "rb") as f:
    ai_model = pickle.load(f)

# Global state storage dictionary and connected WebSocket client connection pool.
node_states = {}
connected_clients = []

# Gateway identifier and geographical anchor coordinates.
GATEWAY_ID = "GATEWAY_01"
GATEWAY_COORDS = TOPOLOGY.get(GATEWAY_ID, {
    "lat": 11.5653,
    "lon": 79.4858,
    "type": "gateway",
    "name": "Pit-Top LoRa Edge Gateway"
})

# Log-distance path loss parameters for 433 MHz LoRa distance estimation.
RSSI_REF_1M = -70.0
PATH_LOSS_EXPONENT = 2.2

# Convert filtered LoRa RSSI to physical distance using log-distance path loss.
def rssi_to_distance(rssi_dbm: float) -> float:
    try:
        exponent = (RSSI_REF_1M - float(rssi_dbm)) / (10.0 * PATH_LOSS_EXPONENT)
        dist = 10.0 ** exponent
        return float(np.clip(dist, 0.2, 50.0))
    except Exception:
        return 1.5

# Recursively convert NumPy numeric types to native Python types for JSON encoding.
def sanitize_for_json(obj):
    if isinstance(obj, (np.bool_, np.bool)):
        return bool(obj)
    elif isinstance(obj, (np.floating, float)):
        val = float(obj)
        return 0.0 if (math.isnan(val) or math.isinf(val)) else val
    elif isinstance(obj, (np.integer, int)):
        return int(obj)
    elif isinstance(obj, np.ndarray):
        return [sanitize_for_json(x) for x in obj.tolist()]
    elif isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(x) for x in obj]
    return obj

# Initialize Kalman filters, geotechnical metrics, and tracking state for a node.
def init_node_state(lat, lon):
    # Initialize 1D Kalman filter for tilt tracking and velocity derivation.
    kf = KalmanFilter(dim_x=1, dim_z=1)
    kf.x = np.array([[0.]])
    kf.F = np.array([[1.]])
    kf.H = np.array([[1.]])
    kf.P = np.array([[10.]])
    kf.R = np.array([[0.05]])
    kf.Q = np.array([[1.0]])
    
    # Initialize 1D Kalman filter for RSSI ranging and noise rejection.
    kf_rssi = KalmanFilter(dim_x=1, dim_z=1)
    kf_rssi.x = np.array([[-65.0]])
    kf_rssi.F = np.array([[1.]])
    kf_rssi.H = np.array([[1.]])
    kf_rssi.P = np.array([[10.]])
    kf_rssi.R = np.array([[1.0]])
    kf_rssi.Q = np.array([[0.5]])
    
    return {
        "lat": float(lat), 
        "lon": float(lon), 
        "kf": kf,
        "kf_rssi": kf_rssi,
        "reading_count": 0,
        "last_packet_ts": None,
        "is_prewarmed": False,
        "history_tilt": [], 
        "history_time": [], 
        "history_velocity": [],
        "baseline_tilt": None,
        "alarm_decay_timer": 0,
        "current_velocity": 0.0, 
        "current_acceleration": 0.0,
        "latest_metrics": {
            "tilt_pitch_deg": 0.0,
            "tilt_roll_deg": 0.0,
            "tilt_total_deg": 0.0,
            "vibration_rms_g": 0.0,
            "vibration_peak_g": 0.0,
            "temp_c": 28.0
        }, 
        "latest_power": {
            "battery_v": 4.1,
            "is_charging": True
        },
        "rf": {
            "rssi_dbm": -65.0,
            "snr_db": 8.5,
            "filtered_rssi_dbm": -65.0
        },
        "baseline_distance": None,
        "current_distance": 1.8,
        "relative_displacement_m": 0.0,
        "baseline_mds": None,
        "mds_coords": {"x": 0.0, "y": 0.0},
        "mds_displacement_m": 0.0,
        "risk_score": 0.0, 
        "fos": 2.5,
        "status": "OFFLINE", 
        "safety_override": False,
        "cumulative_disp": 0.0, 
        "inverse_velocity": 99.9
    }

# Pre-populate sensor node state instances from topology configuration.
for nid, coords in TOPOLOGY.items():
    if coords.get("type", "sensor") == "sensor":
        node_states[nid] = init_node_state(coords["lat"], coords["lon"])

# Compute classical multidimensional scaling coordinates from relative RF distances.
def update_mds_network():
    try:
        # Extract current distances from gateway to sensor nodes.
        d_g1 = float(node_states.get("NODE_01", {}).get("current_distance", 118.0))
        d_g2 = float(node_states.get("NODE_02", {}).get("current_distance", 109.0))
        
        # Estimate inter-node separation using geometric law of cosines.
        cos_theta = (118.0**2 + 109.0**2 - 226.0**2) / (2.0 * 118.0 * 109.0)
        d_12 = math.sqrt(max(1.0, d_g1**2 + d_g2**2 - 2.0 * d_g1 * d_g2 * cos_theta))
        
        # Construct 3x3 squared Euclidean distance matrix.
        D = np.array([
            [0.0, d_g1, d_g2],
            [d_g1, 0.0, d_12],
            [d_g2, d_12, 0.0]
        ], dtype=float)
        
        n = 3
        D2 = D ** 2
        H = np.eye(n) - np.ones((n, n)) / n
        B = -0.5 * H.dot(D2).dot(H)
        
        # Compute eigendecomposition of double-centered Gram matrix.
        eigvals, eigvecs = np.linalg.eigh(B)
        idx = np.argsort(eigvals)[::-1]
        eigvals = eigvals[idx]
        eigvecs = eigvecs[:, idx]
        
        pos_eigs = np.maximum(eigvals[:2], 0.0)
        coords = eigvecs[:, :2] * np.sqrt(pos_eigs)
        coords -= coords[0]
        
        # Update Node 1 relative MDS coordinates and displacement.
        if "NODE_01" in node_states:
            pos1 = np.array([float(coords[1, 0]), float(coords[1, 1])])
            if node_states["NODE_01"].get("baseline_mds") is None:
                node_states["NODE_01"]["baseline_mds"] = pos1
            base1 = node_states["NODE_01"]["baseline_mds"]
            shift1 = float(np.linalg.norm(pos1 - base1))
            node_states["NODE_01"]["mds_coords"] = {"x": round(float(pos1[0]), 2), "y": round(float(pos1[1]), 2)}
            node_states["NODE_01"]["mds_displacement_m"] = round(shift1, 3)
            
        # Update Node 2 relative MDS coordinates and displacement.
        if "NODE_02" in node_states:
            pos2 = np.array([float(coords[2, 0]), float(coords[2, 1])])
            if node_states["NODE_02"].get("baseline_mds") is None:
                node_states["NODE_02"]["baseline_mds"] = pos2
            base2 = node_states["NODE_02"]["baseline_mds"]
            shift2 = float(np.linalg.norm(pos2 - base2))
            node_states["NODE_02"]["mds_coords"] = {"x": round(float(coords[2, 0]), 2), "y": round(float(coords[2, 1]), 2)}
            node_states["NODE_02"]["mds_displacement_m"] = round(shift2, 3)
    except Exception:
        pass

# Pydantic schema models for incoming telemetry validation.
class PowerData(BaseModel):
    battery_v: float
    is_charging: bool

class MetricsData(BaseModel):
    tilt_pitch_deg: float
    tilt_roll_deg: float
    tilt_total_deg: float
    vibration_rms_g: float
    vibration_peak_g: float
    temp_c: float

class RfData(BaseModel):
    rssi_dbm: float = -65.0
    snr_db: float = 8.5

class TelemetryPacket(BaseModel):
    node_id: str
    timestamp: int
    power: PowerData
    metrics: MetricsData
    rf: Optional[RfData] = None

# Construct a 32-point circular GeoJSON polygon feature for hazard visualization.
def create_circle_feature(lon, lat, radius_deg, risk_val, node_id, band_name="core"):
    coords = []
    for angle in np.linspace(0, 2 * np.pi, 33):
        dx = radius_deg * math.cos(angle) / max(0.1, math.cos(math.radians(lat)))
        dy = radius_deg * math.sin(angle)
        coords.append([float(round(lon + dx, 6)), float(round(lat + dy, 6))])
    
    clamped_risk = float(np.clip(risk_val, 0.0, 1.0))
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [coords]
        },
        "properties": {
            "risk": clamped_risk,
            "node_id": str(node_id),
            "band": str(band_name),
            "is_fallback": True
        }
    }

# Generate GeoJSON hazard zones for active nodes exceeding risk thresholds.
def generate_risk_geojson():
    # Filter active nodes with sufficient reading history.
    active_nodes = [
        (nid, s) for nid, s in node_states.items() 
        if s.get("reading_count", 0) >= 2
    ]
    
    features = []
    # Generate multi-tier hazard rings when risk or FoS exceeds warning limits.
    for nid, s in active_nodes:
        risk = float(s.get("risk_score", 0.0))
        fos = float(s.get("fos", 2.50))
        if risk > 0.06 or fos < 2.40:
            base_r = 0.00072
            features.append(create_circle_feature(s["lon"], s["lat"], base_r, risk * 0.45, nid, "fade_halo"))
            features.append(create_circle_feature(s["lon"], s["lat"], base_r * 0.50, risk, nid, "core_epicenter"))

    return {"type": "FeatureCollection", "features": features}

# Assemble complete sanitized system state snapshot for dashboard broadcasting.
def build_state_payload():
    clean_nodes = {}
    global_max_risk = 0.0
    active_alarms = []
    
    for nid, data in node_states.items():
        reading_cnt = int(data.get("reading_count", 0))
        last_pkt = data.get("last_packet_ts")
        last_seen_sec = (int(time.time()) - int(last_pkt)) if last_pkt is not None else 99999
        is_node_offline = bool(reading_cnt == 0 or last_seen_sec > 8)

        risk = float(data.get("risk_score", 0.0))
        override = bool(data.get("safety_override", False))
        battery_v = float(data.get("latest_power", {}).get("battery_v", 4.1))
        is_charging = bool(data.get("latest_power", {}).get("is_charging", True))
        is_battery_critical = bool(data.get("latest_power", {}).get("is_battery_critical", battery_v < 3.4))

        if is_node_offline:
            status = "OFFLINE"
        elif override or risk > 0.65 or float(data.get("fos", 2.5)) < 1.0:
            status = "CRITICAL"
            active_alarms.append({
                "node_id": str(nid),
                "severity": "CRITICAL",
                "trigger": "Velocity Safety Override" if override else "Critical Subsidence Hazard",
                "timestamp": int(time.time())
            })
        elif risk > 0.35 or float(data.get("fos", 2.5)) < 1.5:
            status = "WARNING"
        else:
            status = "STABLE"

        if status != "OFFLINE" and risk > global_max_risk:
            global_max_risk = risk

        clean_nodes[nid] = {
            "lat": float(data["lat"]), 
            "lon": float(data["lon"]),
            "power": {
                "battery_v": battery_v,
                "is_charging": is_charging,
                "is_battery_critical": is_battery_critical
            },
            "metrics": {
                "tilt_pitch_deg": float(data.get("latest_metrics", {}).get("tilt_pitch_deg", 0.0)),
                "tilt_roll_deg": float(data.get("latest_metrics", {}).get("tilt_roll_deg", 0.0)),
                "tilt_total_deg": float(data.get("latest_metrics", {}).get("tilt_total_deg", 0.0)),
                "vibration_rms_g": float(data.get("latest_metrics", {}).get("vibration_rms_g", 0.0)),
                "vibration_peak_g": float(data.get("latest_metrics", {}).get("vibration_peak_g", 0.0)),
                "temp_c": float(data.get("latest_metrics", {}).get("temp_c", 28.0))
            },
            "rf": {
                "rssi_dbm": float(data.get("rf", {}).get("rssi_dbm", -65.0)),
                "snr_db": float(data.get("rf", {}).get("snr_db", 8.5)),
                "filtered_rssi_dbm": float(data.get("rf", {}).get("filtered_rssi_dbm", -65.0))
            },
            "distance_m": round(float(data.get("current_distance", 115.0)), 2),
            "relative_displacement_m": round(float(data.get("relative_displacement_m", 0.0)), 3),
            "mds_coords": data.get("mds_coords", {"x": 0.0, "y": 0.0}),
            "mds_displacement_m": round(float(data.get("mds_displacement_m", 0.0)), 3),
            "velocity": round(float(data.get("current_velocity", 0.0)), 3),
            "acceleration": round(float(data.get("current_acceleration", 0.0)), 3),
            "cumulative_disp": round(float(data.get("cumulative_disp", 0.0)), 3),
            "inverse_velocity": round(float(data.get("inverse_velocity", 99.9)), 2),
            "risk_score": round(risk, 4),
            "fos": round(float(data.get("fos", 2.5)), 2),
            "status": status,
            "safety_override": override,
            "reading_count": reading_cnt,
            "is_prewarmed": bool(data.get("is_prewarmed", False)),
            "last_seen_sec": last_seen_sec,
            "subsidence_duration_sec": round(float(data.get("subsidence_duration_sec", 0.0)), 1),
            "history_tilt": [float(x) for x in list(data.get("history_tilt", []))[-15:]]
        }
        
    # Detect multi-bench geotechnical hazard propagation across adjacent nodes.
    active_hazard_nodes = [
        str(nid) for nid, d in node_states.items()
        if (float(d.get("risk_score", 0.0)) > 0.60 or str(d.get("status")) == "CRITICAL")
        and (float(d.get("current_velocity", 0.0)) > 4.0 or float(d.get("fos", 2.5)) < 1.20)
    ]
    is_spreading = bool(len(active_hazard_nodes) >= 2)
    if is_spreading:
        global_max_risk = min(0.99, max(global_max_risk * 1.15, 0.92))
        active_alarms.append({
            "node_id": "MULTI_NODE_SPREADING",
            "severity": "CRITICAL_RUNAWAY",
            "trigger": "Multi-Bench Geotechnical Hazard Spreading",
            "nodes_involved": active_hazard_nodes,
            "timestamp": int(time.time())
        })

    # Determine global operational safety status from node conditions.
    online_nodes_count = sum(1 for d in clean_nodes.values() if d.get("status") != "OFFLINE")
    if any(d.get("status") == "CRITICAL" for d in clean_nodes.values()) or is_spreading:
        global_status = "CRITICAL"
    elif online_nodes_count == 0:
        global_status = "OFFLINE"
    else:
        global_status = "STABLE"

    # Construct gateway metadata and live RF mesh link metrics.
    gateway_payload = {
        "node_id": GATEWAY_ID,
        "name": GATEWAY_COORDS.get("name", "Safe Pit-Top Elevated LoRa Mast"),
        "lat": float(GATEWAY_COORDS["lat"]),
        "lon": float(GATEWAY_COORDS["lon"]),
        "status": "ONLINE (USB SERIAL BRIDGE)",
        "last_seen": int(time.time()),
        "rf_links": [
            {
                "source": nid,
                "target": GATEWAY_ID,
                "source_coords": [float(data["lat"]), float(data["lon"])],
                "target_coords": [float(GATEWAY_COORDS["lat"]), float(GATEWAY_COORDS["lon"])],
                "rssi_dbm": float(data.get("rf", {}).get("filtered_rssi_dbm", -65.0)),
                "snr_db": float(data.get("rf", {}).get("snr_db", 8.5)),
                "distance_m": round(float(data.get("current_distance", 115.0)), 1),
                "rel_displacement_m": round(float(data.get("relative_displacement_m", 0.0)), 3),
                "mds_displacement_m": round(float(data.get("mds_displacement_m", 0.0)), 3),
                "status": "ACTIVE" if data.get("reading_count", 0) > 0 and data.get("last_packet_ts") is not None and (int(time.time()) - int(data.get("last_packet_ts"))) <= 8 else "OFFLINE"
            }
            for nid, data in node_states.items()
        ]
    }
        
    raw_payload = {
        "type": "STATE_SNAPSHOT",
        "timestamp": int(time.time()),
        "global_status": global_status,
        "is_spreading": is_spreading,
        "active_hazard_nodes": active_hazard_nodes,
        "nodes": clean_nodes,
        "gateway": gateway_payload,
        "heatmap": generate_risk_geojson(),
        "active_alarms": active_alarms
    }
    return sanitize_for_json(raw_payload)

# Reset all sensor node tracking states to nominal baseline.
@app.post("/api/reset")
async def reset_simulation_state():
    global node_states
    for nid, coords in TOPOLOGY.items():
        if coords.get("type", "sensor") == "sensor":
            node_states[nid] = init_node_state(coords["lat"], coords["lon"])
    await broadcast_state()
    return {"status": "success", "message": "All node states reset to nominal"}

class MovementTrigger(BaseModel):
    node_id: Optional[str] = "NODE_01"
    tilt_spike: Optional[float] = 4.5
    vib_spike: Optional[float] = 0.25

# Inject simulated motion impulse packet for live demonstration.
@app.post("/api/trigger_movement")
async def trigger_movement(req: MovementTrigger):
    nid = req.node_id if req.node_id in node_states else "NODE_01"
    pkt = TelemetryPacket(
        node_id=nid,
        timestamp=int(time.time()),
        power=PowerData(battery_v=4.05, is_charging=True),
        metrics=MetricsData(
            tilt_pitch_deg=round(req.tilt_spike * 0.65, 2),
            tilt_roll_deg=round(req.tilt_spike * 0.45, 2),
            tilt_total_deg=float(req.tilt_spike),
            vibration_rms_g=float(req.vib_spike * 0.6),
            vibration_peak_g=float(req.vib_spike),
            temp_c=29.2
        ),
        rf=RfData(rssi_dbm=-64.0, snr_db=9.2)
    )
    await process_single_node_packet(pkt, is_paired=True)
    return {"status": "success", "message": f"Simulated motion impulse triggered on {nid}"}

# Endpoint for receiving telemetry packets from sensor nodes or gateway.
@app.post("/api/telemetry")
async def receive_telemetry(packet: TelemetryPacket):
    return await process_single_node_packet(packet, is_paired=False)

# Process incoming sensor packet through Kalman filters, geotechnical math, and AI model.
async def process_single_node_packet(packet: TelemetryPacket, is_paired=False):
    nid = packet.node_id
    if not is_paired:
        print(f"[RECV] {nid} | Tilt={packet.metrics.tilt_total_deg:.2f}° | Vib={packet.metrics.vibration_peak_g:.4f}g | Temp={packet.metrics.temp_c:.1f}°C")
    if nid not in TOPOLOGY or TOPOLOGY[nid].get("type") == "gateway":
        return {"error": "Unknown or invalid Sensor Node"}
    
    if nid not in node_states:
        node_states[nid] = init_node_state(TOPOLOGY[nid]["lat"], TOPOLOGY[nid]["lon"])
        
    state = node_states[nid]

    # Deduplicate rapid concurrent submissions across Wi-Fi and serial.
    now_ts = time.time()
    last_ingest = state.get("last_ingest_time", 0.0)
    last_m = state.get("latest_metrics", {})
    is_exact_dup = (
        (now_ts - last_ingest < 0.05) and
        abs(float(packet.metrics.tilt_pitch_deg) - float(last_m.get("tilt_pitch_deg", 999))) < 0.002 and
        abs(float(packet.metrics.tilt_roll_deg) - float(last_m.get("tilt_roll_deg", 999))) < 0.002 and
        abs(float(packet.metrics.vibration_peak_g) - float(last_m.get("vibration_peak_g", 999))) < 0.0005
    )
    if is_exact_dup:
        return {"status": "deduplicated"}
    state["last_ingest_time"] = now_ts

    raw_tilt = float(packet.metrics.tilt_total_deg)
    pkt_time = int(time.time())
    state["last_packet_ts"] = pkt_time
    state["reading_count"] = int(state.get("reading_count", 0)) + 1
    
    # Filter raw tilt through 1D Kalman filter.
    if len(state["history_tilt"]) == 0:
        state["kf"].x = np.array([[raw_tilt]])
        state["baseline_tilt"] = raw_tilt
        
    state["kf"].predict()
    state["kf"].update(np.array([[raw_tilt]]))
    filtered_tilt = float(state["kf"].x[0][0]) 
    
    # Filter raw RSSI through 1D Kalman filter and compute displacement.
    raw_rssi = float(packet.rf.rssi_dbm) if packet.rf else -65.0
    raw_snr = float(packet.rf.snr_db) if packet.rf else 8.5
    
    state["kf_rssi"].predict()
    state["kf_rssi"].update(np.array([[raw_rssi]]))
    filtered_rssi = float(state["kf_rssi"].x[0][0])
    
    calc_distance = rssi_to_distance(filtered_rssi)
    if state.get("baseline_distance") is None:
        state["baseline_distance"] = calc_distance
        
    rel_displacement_rf = calc_distance - state["baseline_distance"]
    
    state["rf"] = {
        "rssi_dbm": round(raw_rssi, 1),
        "snr_db": round(raw_snr, 1),
        "filtered_rssi_dbm": round(filtered_rssi, 1)
    }
    state["current_rssi"] = round(filtered_rssi, 1)
    state["current_distance"] = round(calc_distance, 2)
    state["relative_displacement_m"] = round(rel_displacement_rf, 3)
    
    # Update multidimensional scaling coordinates from relative RF shifts.
    update_mds_network()
    
    # Append filtered tilt to historical rolling window buffer.
    state["history_tilt"].append(filtered_tilt)
    state["history_time"].append(pkt_time)
    
    if len(state["history_tilt"]) > 10:
        state["history_tilt"].pop(0)
        state["history_time"].pop(0)
        
    cumulative_displacement = float(abs(filtered_tilt - state["baseline_tilt"]))
        
    # Pre-warm Kalman filter state on initial packet.
    if state["reading_count"] < 2:
        state["is_prewarmed"] = False
        state["current_velocity"] = 0.0
        state["current_acceleration"] = 0.0
        state["latest_metrics"] = packet.metrics.dict()
        state["latest_metrics"]["tilt_total_deg"] = filtered_tilt
        state["latest_power"] = packet.power.dict()
        state["risk_score"] = 0.0
        state["fos"] = 2.50
        state["status"] = "CALIBRATING"
        state["safety_override"] = False
        state["cumulative_disp"] = 0.0
        state["inverse_velocity"] = 99.9
        
        await broadcast_state()
        return {"status": "calibrating", "reading_count": state["reading_count"], "risk_score": 0.0}

    state["is_prewarmed"] = True

    # Calculate dynamic velocity with sensor deadband and ambient noise rejection.
    prev_tilt = state["history_tilt"][-2] if len(state["history_tilt"]) >= 2 else filtered_tilt
    dynamic_tilt_delta = float(abs(filtered_tilt - prev_tilt))
    
    vib_peak = float(packet.metrics.vibration_peak_g)
    vib_rms = float(packet.metrics.vibration_rms_g)
    
    if dynamic_tilt_delta < 0.12:
        effective_tilt_delta = 0.0
    else:
        effective_tilt_delta = dynamic_tilt_delta - 0.10

    excess_vib = max(0.0, vib_peak - 0.12)
    
    instant_velocity = float(round(effective_tilt_delta * 22.0 + (excess_vib * 12.0), 2))
    state["current_velocity"] = instant_velocity
    state["current_acceleration"] = float(round(effective_tilt_delta * 50.0, 1))

    # Detect active physical slope motion and update duration timer.
    is_active_motion = bool(effective_tilt_delta > 0.18 or excess_vib > 0.10)

    if is_active_motion:
        state["last_motion_time"] = now_ts
        if state.get("subsidence_start_ts") is None:
            state["subsidence_start_ts"] = now_ts
        state["subsidence_duration_sec"] = float(round(now_ts - state["subsidence_start_ts"], 1))

        # Compute factor of safety based on tilt deviation, vibration, and velocity.
        excess_tilt_dev = max(0.0, abs(filtered_tilt - state.get("baseline_tilt", filtered_tilt)) - 1.8)
        fos_tilt_penalty = excess_tilt_dev * 0.28
        fos_vib_penalty = excess_vib * 3.0
        fos_vel_penalty = min(0.8, instant_velocity * 0.03)
        instant_fos = 2.50 - fos_tilt_penalty - fos_vib_penalty - fos_vel_penalty
        instant_fos = float(round(np.clip(instant_fos, 0.35, 2.50), 2))
        state["sustain_fos"] = min(state.get("sustain_fos", 2.50), instant_fos)
        fos = instant_fos
    else:
        # Restore nominal factor of safety when motion ceases.
        time_since_motion = now_ts - float(state.get("last_motion_time", 0.0))
        if time_since_motion < 2.5 and state.get("sustain_fos", 2.50) < 2.30:
            fos = float(round(state.get("sustain_fos", 2.50), 2))
        else:
            fos = 2.50
            state["sustain_fos"] = 2.50
            state["subsidence_start_ts"] = None
            state["subsidence_duration_sec"] = 0.0
            state["baseline_tilt"] = float(0.85 * state.get("baseline_tilt", filtered_tilt) + 0.15 * filtered_tilt)

    state["fos"] = fos

    # Run inference using trained XGBoost geotechnical risk model.
    ml_hazard_prob = 0.02
    try:
        if ai_model is not None:
            if instant_velocity == 0.0 and excess_vib == 0.0:
                ml_hazard_prob = 0.02
            else:
                tilt_dev = float(abs(filtered_tilt - state.get("baseline_tilt", filtered_tilt)))
                features = np.array([[
                    float(min(tilt_dev, 45.0)),
                    float(instant_velocity),
                    float(vib_rms),
                    float(vib_peak)
                ]])
                probs = ai_model.predict_proba(features)
                ml_hazard_prob = float(probs[0][1])
    except Exception:
        ml_hazard_prob = 0.02

    # Map factor of safety and ML model probability to combined hazard score.
    if fos >= 1.5:
        risk_from_fos = (2.50 - fos) / 1.0 * 0.35
    elif fos >= 1.0:
        risk_from_fos = 0.35 + ((1.50 - fos) / 0.50) * 0.35
    else:
        risk_from_fos = 0.70 + ((1.00 - fos) / 0.65) * 0.28
        
    probability = float(round(np.clip(max(risk_from_fos, ml_hazard_prob), 0.02, 0.98), 3))
    is_override = bool(fos < 1.0 or probability > 0.70)
    
    # Discretize continuous risk score into operational alert category.
    if probability > 0.65:
        node_status = "CRITICAL"
    elif probability > 0.35:
        node_status = "WARNING"
    else:
        node_status = "STABLE"

    cumulative_displacement = float(round(abs(filtered_tilt - state.get("baseline_tilt", filtered_tilt)), 3))
    inverse_velocity = float(round(1.0 / state["current_velocity"], 2)) if state["current_velocity"] > 0.01 else 99.9

    # Commit updated geotechnical metrics and broadcast state to clients.
    state["latest_metrics"] = packet.metrics.dict()
    state["latest_metrics"]["tilt_total_deg"] = float(round(raw_tilt, 2))
    state["latest_metrics"]["filtered_tilt_deg"] = float(round(filtered_tilt, 2))
    state["latest_power"] = packet.power.dict()
    state["risk_score"] = float(probability)
    state["fos"] = float(max(0.1, fos))
    state["status"] = str(node_status)
    state["safety_override"] = bool(is_override)
    state["cumulative_disp"] = float(cumulative_displacement)
    state["inverse_velocity"] = float(inverse_velocity)
    
    await broadcast_state()
    return {"status": "success", "risk_score": probability}

# Broadcast current system state snapshot to all connected WebSocket clients.
async def broadcast_state():
    if not connected_clients: return
    payload = build_state_payload()
    json_str = json.dumps(payload)
    
    dead_clients = []
    for client in connected_clients:
        try: 
            await client.send_text(json_str)
        except Exception:
            dead_clients.append(client)
            
    for dead in dead_clients:
        if dead in connected_clients:
            connected_clients.remove(dead)

# Handle real-time WebSocket connection, instant state hydration, and ping-pong latency.
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    try:
        snapshot = build_state_payload()
        await websocket.send_text(json.dumps(snapshot))
        
        while True:
            msg = await websocket.receive_text()
            try:
                data = json.loads(msg)
                if data.get("type") == "PING":
                    await websocket.send_text(json.dumps({
                        "type": "PONG",
                        "client_timestamp": data.get("client_timestamp", 0),
                        "server_timestamp": int(time.time() * 1000)
                    }))
            except Exception:
                pass
    except WebSocketDisconnect:
        pass
    except Exception as ex:
        print(f"[WS ERROR] {type(ex).__name__}: {ex}")
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)

# Serve GIS Operator Command Center interface.
@app.get("/")
async def serve_index():
    return FileResponse("frontend/index.html")

# Serve Engineering Diagnostics and telemetry analysis interface.
@app.get("/engineering")
async def serve_engineering():
    return FileResponse("frontend/engineering.html")

# Return current global state snapshot over HTTP GET.
@app.get("/api/state")
async def get_state_http():
    return build_state_payload()

app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# Background worker reading live LoRa telemetry from USB serial bridge and streaming to dashboard.
async def serial_monitor_loop():
    if serial is None:
        print("[SERIAL BRIDGE] pyserial not installed. Skipping hardware USB serial monitor loop.")
        return
    print("[SERIAL BRIDGE] Background monitor started. Watching for USB ESP32 devices...")
    loop = asyncio.get_event_loop()
    
    while True:
        ser = None
        try:
            # Discover available USB COM ports on host system.
            available = [p.device for p in serial.tools.list_ports.comports() if "COM" in p.device]
            if not available:
                await asyncio.sleep(2.0)
                continue
            
            port_to_use = "COM7" if "COM7" in available else available[0]
            
            # Open selected COM port with non-blocking low-latency timeout.
            ser = serial.Serial()
            ser.port = port_to_use
            ser.baudrate = 115200
            ser.timeout = 0.04
            ser.dtr = False
            ser.rts = False
            ser.open()
            print(f"[SERIAL BRIDGE] Successfully opened {port_to_use} for live low-latency wire telemetry.")
            
            active_rf_cache = {
                "NODE_01": {"rssi": -65.0, "snr": 9.5},
                "NODE_02": {"rssi": -68.0, "snr": 8.5},
                "NODE_03": {"rssi": -67.0, "snr": 9.0}
            }
            last_parsed_node = "NODE_01"

            while ser.is_open:
                # Clear backlog if serial input buffer is trailing behind.
                if ser.in_waiting > 200:
                    ser.reset_input_buffer()

                # Read and decode serial telemetry line.
                line_bytes = await loop.run_in_executor(None, ser.readline)
                if not line_bytes:
                    await asyncio.sleep(0.005)
                    continue
                
                try:
                    line = line_bytes.decode("utf-8", errors="replace").strip()
                except Exception:
                    continue
                
                if not line:
                    continue
                print(f"[COM7 RAW] {line}")

                # Parse atomic packet tag format for fast packet decoding.
                raw_pkt = None
                pkt_rssi = -68.0
                pkt_snr = 9.0

                if "[PKT]" in line:
                    try:
                        content = line.split("[PKT]")[1].strip()
                        segments = content.split("|")
                        raw_pkt = segments[0].strip()
                        for seg in segments[1:]:
                            if "RSSI=" in seg:
                                pkt_rssi = float(seg.split("RSSI=")[1])
                            elif "SNR=" in seg:
                                pkt_snr = float(seg.split("SNR=")[1])
                    except Exception:
                        raw_pkt = None

                # Fallback parser for standard multi-line serial output.
                if not raw_pkt:
                    if "RSSI:" in line:
                        try:
                            clean_rssi = float(line.split("RSSI:")[1].replace("dBm", "").strip())
                            if last_parsed_node in active_rf_cache:
                                active_rf_cache[last_parsed_node]["rssi"] = clean_rssi
                        except Exception:
                            pass
                    elif "SNR:" in line:
                        try:
                            clean_snr = float(line.split("SNR:")[1].replace("dB", "").strip())
                            if last_parsed_node in active_rf_cache:
                                active_rf_cache[last_parsed_node]["snr"] = clean_snr
                        except Exception:
                            pass
                    
                    if "Raw:" in line:
                        raw_pkt = line.split("Raw:")[1].strip()
                    elif line.startswith("N1,") or line.startswith("N2,") or line.startswith("N3,"):
                        raw_pkt = line
                
                # Extract sensor fields and dispatch validated telemetry packet.
                if raw_pkt and ("," in raw_pkt):
                    parts = [p.strip() for p in raw_pkt.split(",")]
                    if len(parts) >= 8 and parts[0] in ["N1", "N2", "N3"]:
                        node_id = f"NODE_{int(parts[0][1:]):02d}"
                        last_parsed_node = node_id
                        try:
                            pitch = float(parts[2])
                            roll = float(parts[3])
                            tilt = float(parts[4])
                            vib_rms = float(parts[5])
                            vib_peak = float(parts[6])
                            temp = float(parts[7])
                            
                            active_rf_cache[node_id] = {"rssi": pkt_rssi, "snr": pkt_snr}
                            pkt = TelemetryPacket(
                                node_id=node_id,
                                timestamp=int(time.time()),
                                power=PowerData(battery_v=4.1, is_charging=True),
                                metrics=MetricsData(
                                    tilt_pitch_deg=pitch,
                                    tilt_roll_deg=roll,
                                    tilt_total_deg=tilt,
                                    vibration_rms_g=vib_rms,
                                    vibration_peak_g=vib_peak,
                                    temp_c=temp
                                ),
                                rf=RfData(rssi_dbm=pkt_rssi, snr_db=pkt_snr)
                            )
                            await receive_telemetry(pkt)
                        except Exception as parse_ex:
                            pass
        except Exception as ex:
            await asyncio.sleep(2.0)
        finally:
            if ser and ser.is_open:
                try:
                    ser.close()
                except Exception:
                    pass

# Start background serial monitor worker on application startup.
@app.on_event("startup")
async def on_startup():
    asyncio.create_task(serial_monitor_loop())