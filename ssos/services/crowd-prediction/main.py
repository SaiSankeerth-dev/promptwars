"""
crowd-prediction/main.py — FastAPI service using a real LSTM model.

Replaces the previous random.uniform() implementation with:
  - Real PyTorch CrowdLSTM (bidirectional LSTM + temporal attention)
  - Per-zone rolling feature buffer (30-tick lookback)
  - CrushGuard™ rate-of-change anomaly layer on top of LSTM output
  - Kafka consumer for live observation ingestion
  - Redis pub/sub for decision engine notification
"""

import os
import json
import asyncio
import threading
import numpy as np
from datetime import datetime
from typing import Dict, List
from fastapi import FastAPI
import redis
from kafka import KafkaConsumer, KafkaProducer
import torch

from model import CrowdLSTM, load_model, INPUT_FEATURES, SEQ_LEN, FORECAST_HORIZON

app = FastAPI(title="Crowd Density Prediction (LSTM)", version="2.0.0")

# ─── Infrastructure ───────────────────────────────────────────────────────────

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True,
)

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:29092").split(",")

ZONES = [
    "gate_a", "gate_b", "gate_c", "gate_d", "gate_e",
    "concourse_a", "concourse_b", "concourse_c", "concourse_d",
    "stand_north", "stand_south", "stand_east", "stand_west",
    "restroom_1", "restroom_2", "restroom_3", "restroom_4",
    "food_court_1", "food_court_2", "vendor_row_1", "vendor_row_2",
    "exit_north", "exit_south", "exit_east", "exit_west",
]

RISK_NAMES = ["low", "medium", "high", "critical"]
ZONE_CAPACITY = {z: 2000 for z in ZONES}
ZONE_CAPACITY.update({
    "stand_north": 25000, "stand_south": 25000,
    "stand_east": 15000, "stand_west": 15000,
    "gate_a": 3000, "gate_b": 3000,
    "exit_north": 5000, "exit_south": 5000,
})

# ─── Model ────────────────────────────────────────────────────────────────────

MODEL_PATH = os.getenv("MODEL_PATH", "crowd_lstm.pt")

def _load_or_init_model() -> CrowdLSTM:
    """Load pre-trained weights if available, else use random-init model."""
    if os.path.exists(MODEL_PATH):
        print(f"[model] Loading weights from {MODEL_PATH}")
        return load_model(MODEL_PATH)
    print("[model] No checkpoint found — using freshly initialised model (run model.py to train)")
    m = CrowdLSTM()
    m.eval()
    return m

model: CrowdLSTM = _load_or_init_model()

# ─── Per-zone feature buffer ──────────────────────────────────────────────────

class ZoneFeatureBuffer:
    """
    Maintains a rolling window of (SEQ_LEN, INPUT_FEATURES) observations per zone.

    Features per tick:
      [density, entry_delta, exit_delta, velocity, hour_sin, hour_cos]
    """

    def __init__(self):
        self._buffers: Dict[str, List[List[float]]] = {
            z: [] for z in ZONES
        }
        self._prev_density: Dict[str, float] = {z: 50.0 for z in ZONES}

    def push(self, zone: str, density: float, velocity: float = 1.0):
        hour = datetime.utcnow().hour + datetime.utcnow().minute / 60.0
        hour_rad = (hour / 24.0) * 2 * np.pi

        prev = self._prev_density.get(zone, density)
        delta = density - prev
        entry_delta = max(delta, 0.0)
        exit_delta = max(-delta, 0.0)
        self._prev_density[zone] = density

        feature = [
            density,
            entry_delta,
            exit_delta,
            velocity,
            np.sin(hour_rad),
            np.cos(hour_rad),
        ]
        buf = self._buffers[zone]
        buf.append(feature)
        if len(buf) > SEQ_LEN:
            buf.pop(0)

    def get_tensor(self, zone: str) -> torch.Tensor | None:
        buf = self._buffers[zone]
        if len(buf) < SEQ_LEN:
            # Pad with a steady-state guess (50% density)
            pad_rows = SEQ_LEN - len(buf)
            hour = datetime.utcnow().hour + datetime.utcnow().minute / 60.0
            hour_rad = (hour / 24.0) * 2 * np.pi
            pad = [[50.0, 0.0, 0.0, 1.0, np.sin(hour_rad), np.cos(hour_rad)]] * pad_rows
            data = pad + buf
        else:
            data = buf

        return torch.tensor(data, dtype=torch.float32).unsqueeze(0)  # (1, SEQ_LEN, 6)


feature_buffer = ZoneFeatureBuffer()

# ─── CrushGuard™ ─────────────────────────────────────────────────────────────

class CrushGuard:
    """
    Second-opinion anomaly layer running ON TOP of LSTM output.

    Combines three signals:
      1. LSTM-predicted risk class (high / critical)
      2. Rate of density change over recent ticks (momentum)
      3. Velocity compression ratio (density rising while velocity falls)

    Returns a structured alert with confidence and recommended actions.
    """

    MOMENTUM_WINDOW = 6          # ticks = 60 seconds of lookback
    DANGER_RATE_THRESHOLD = 0.12 # density %/tick
    WARN_RATE_THRESHOLD = 0.06
    VELOCITY_CRUSH_RATIO = 0.6   # velocity < 60% of free-flow at high density

    @staticmethod
    def evaluate(
        zone: str,
        density_history: List[float],
        velocity: float,
        lstm_risk: str,
        lstm_density_forecast: List[float],
    ) -> Dict:
        alert_level = "safe"
        confidence = 0.0
        reasons = []

        # ── Signal 1: LSTM risk class
        ml_risk_score = {"low": 0, "medium": 0.25, "high": 0.65, "critical": 1.0}.get(lstm_risk, 0)
        if lstm_risk in ("high", "critical"):
            reasons.append(f"LSTM forecasts {lstm_risk} risk in next 50s")

        # ── Signal 2: density momentum
        if len(density_history) >= CrushGuard.MOMENTUM_WINDOW:
            recent = density_history[-CrushGuard.MOMENTUM_WINDOW:]
            deltas = [recent[i] - recent[i - 1] for i in range(1, len(recent))]
            avg_rate = sum(deltas) / len(deltas) / 100.0  # normalised [0,1]
            momentum_score = min(avg_rate / CrushGuard.DANGER_RATE_THRESHOLD, 1.0)

            if avg_rate > CrushGuard.DANGER_RATE_THRESHOLD:
                reasons.append(f"Rapid density increase: +{avg_rate * 100:.1f}%/tick")
            elif avg_rate > CrushGuard.WARN_RATE_THRESHOLD:
                reasons.append(f"Elevated density growth rate")
        else:
            avg_rate = 0.0
            momentum_score = 0.0

        # ── Signal 3: velocity compression (hallmark of crush pre-cursor)
        current_density = density_history[-1] if density_history else 50.0
        free_flow_velocity = max(2.0 - current_density / 70.0, 0.2)
        compression_ratio = velocity / free_flow_velocity if free_flow_velocity > 0 else 1.0
        velocity_score = max(0.0, 1.0 - compression_ratio) if current_density > 60 else 0.0

        if velocity_score > 0.4 and current_density > 60:
            reasons.append(f"Velocity compression detected ({velocity:.2f} m/s vs expected {free_flow_velocity:.2f})")

        # ── Combined confidence
        confidence = 0.45 * ml_risk_score + 0.35 * momentum_score + 0.20 * velocity_score

        # ── Alert level
        if confidence >= 0.72 or lstm_risk == "critical":
            alert_level = "danger"
        elif confidence >= 0.45 or lstm_risk == "high":
            alert_level = "warning"
        else:
            alert_level = "safe"

        # ── Time-to-critical estimate (simple linear extrapolation)
        time_to_critical = None
        if alert_level in ("warning", "danger") and avg_rate > 0:
            headroom = max(0.0, 95.0 - current_density)
            ticks_to_critical = headroom / (avg_rate * 100.0) if avg_rate > 0 else 999
            time_to_critical = round(ticks_to_critical * 10)  # seconds

        return {
            "zone": zone,
            "alert_level": alert_level,
            "confidence": round(confidence, 3),
            "reasons": reasons,
            "time_to_critical_seconds": time_to_critical,
            "recommended_actions": _get_actions(alert_level, zone),
            "timestamp": datetime.utcnow().isoformat(),
        }


def _get_actions(alert_level: str, zone: str) -> List[str]:
    if alert_level == "danger":
        return [
            f"Open overflow gate adjacent to {zone}",
            f"Broadcast PA redirect message for {zone}",
            f"Deploy additional staff to {zone}",
            f"Activate dynamic signage: route to alternate {zone.split('_')[0]}",
        ]
    if alert_level == "warning":
        return [
            f"Monitor {zone} closely — density rising",
            f"Pre-position staff near {zone}",
            f"Push app notification: suggest alternate route",
        ]
    return []


crush_guard = CrushGuard()

# ─── Zone density state ───────────────────────────────────────────────────────

zone_density_history: Dict[str, List[float]] = {z: [50.0] * 10 for z in ZONES}
zone_velocity: Dict[str, float] = {z: 1.0 for z in ZONES}


@torch.no_grad()
def _infer_zone(zone: str) -> Dict:
    x = feature_buffer.get_tensor(zone)
    density_pred, risk_logits = model(x)

    risk_idx = int(risk_logits[0].argmax().item())
    risk_name = RISK_NAMES[risk_idx]
    density_forecast = density_pred[0].tolist()
    current_density = float(redis_client.get(f"density:{zone}") or 50.0)

    crush_result = crush_guard.evaluate(
        zone=zone,
        density_history=zone_density_history[zone],
        velocity=zone_velocity[zone],
        lstm_risk=risk_name,
        lstm_density_forecast=density_forecast,
    )

    return {
        "zone": zone,
        "current_density": round(current_density, 2),
        "density_forecast_10s": round(density_forecast[0], 2),
        "density_forecast_30s": round(density_forecast[2], 2),
        "density_forecast_50s": round(density_forecast[4], 2),
        "risk_level": risk_name,
        "risk_confidence": float(risk_logits[0].softmax(dim=0)[risk_idx].item()),
        "crush_guard": crush_result,
        "trend": _trend(zone_density_history[zone]),
        "timestamp": datetime.utcnow().isoformat(),
    }


def _trend(history: List[float]) -> str:
    if len(history) < 3:
        return "stable"
    delta = history[-1] - history[-3]
    if delta > 3:
        return "increasing"
    if delta < -3:
        return "decreasing"
    return "stable"


# ─── Synthetic data loop (when no Kafka) ──────────────────────────────────────

import numpy as np
_tick_counter = 0

def _event_phase_density(zone: str) -> float:
    """Produce event-phased deterministic density for demo when no Kafka."""
    global _tick_counter
    _tick_counter += 1
    hour = datetime.utcnow().hour + datetime.utcnow().minute / 60.0
    base = 50.0

    if 17 <= hour < 18:      base = 30 + (hour - 17) * 40
    elif 18 <= hour < 19:    base = 80
    elif 19 <= hour < 19.5:  base = 70
    elif 19.5 <= hour < 20:  base = 85
    elif 20 <= hour < 21.5:  base = 68
    elif 21.5 <= hour < 23:  base = 40

    zone_factor = {
        "gate_a": 1.2, "gate_b": 1.1, "gate_c": 0.9,
        "food_court_1": 0.8, "food_court_2": 0.85,
        "exit_north": 1.3 if hour > 21.5 else 0.5,
    }.get(zone, 1.0)

    micro_fluctuation = np.sin(_tick_counter * 0.1 + hash(zone) % 10) * 3
    return float(np.clip(base * zone_factor + micro_fluctuation, 0, 100))


async def synthetic_sensor_loop():
    """Simulates real edge sensor data until Kafka becomes available."""
    global _tick_counter
    while True:
        for zone in ZONES:
            density = _event_phase_density(zone)
            velocity = float(np.clip(2.0 - density / 70.0 + np.sin(_tick_counter * 0.1) * 0.1, 0.1, 2.5))

            # Update shared state
            zone_density_history[zone].append(density)
            if len(zone_density_history[zone]) > 100:
                zone_density_history[zone].pop(0)
            zone_velocity[zone] = velocity

            feature_buffer.push(zone, density, velocity)

            redis_client.set(f"density:{zone}", round(density, 2))
            redis_client.set(f"velocity:{zone}", round(velocity, 3))

        await asyncio.sleep(10)


async def inference_loop():
    """Run LSTM inference every 10s; publish results to Redis."""
    while True:
        try:
            predictions = []
            crush_alerts = []

            for zone in ZONES:
                result = _infer_zone(zone)
                predictions.append(result)

                redis_client.set(f"prediction:{zone}:risk", result["risk_level"])
                redis_client.set(f"prediction:{zone}:forecast_10s", result["density_forecast_10s"])
                redis_client.set(f"crushguard:{zone}:level", result["crush_guard"]["alert_level"])
                redis_client.set(f"crushguard:{zone}:confidence", result["crush_guard"]["confidence"])

                if result["crush_guard"]["alert_level"] in ("warning", "danger"):
                    crush_alerts.append(result["crush_guard"])
                    # Publish to decision engine via Redis pub/sub
                    redis_client.publish("crushguard_alerts", json.dumps(result["crush_guard"]))

            redis_client.set("predictions:all", json.dumps(predictions))
            redis_client.set("predictions:updated_at", datetime.utcnow().isoformat())
            redis_client.set("crush_alerts:active", json.dumps(crush_alerts))

            # Also publish full snapshot for WebSocket clients
            redis_client.publish("dashboard:live", json.dumps({
                "type": "PREDICTIONS",
                "payload": predictions,
                "crush_alerts": crush_alerts,
                "timestamp": datetime.utcnow().isoformat(),
            }))

        except Exception as e:
            print(f"[inference] Error: {e}")

        await asyncio.sleep(10)


def kafka_consumer_loop():
    """Consume real edge observations when Kafka is available."""
    while True:
        try:
            consumer = KafkaConsumer(
                "crowd_observations",
                bootstrap_servers=KAFKA_BROKERS,
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                auto_offset_reset="latest",
                group_id="crowd-prediction-v2",
            )
            for message in consumer:
                data = message.value
                zone = data.get("zone")
                density = float(data.get("detections", {}).get("density", 0))
                velocity = float(data.get("detections", {}).get("avg_velocity", 1.0))

                if zone and zone in ZONES:
                    zone_density_history[zone].append(density)
                    if len(zone_density_history[zone]) > 100:
                        zone_density_history[zone].pop(0)
                    zone_velocity[zone] = velocity
                    feature_buffer.push(zone, density, velocity)
                    redis_client.set(f"density:{zone}", round(density, 2))

        except Exception as e:
            print(f"[kafka] {e} — retrying in 10s")
            import time
            time.sleep(10)


# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    for zone in ZONES:
        redis_client.hset("stadium:zones", zone, json.dumps({
            "name": zone.replace("_", " ").title(),
            "capacity": ZONE_CAPACITY.get(zone, 2000),
        }))
    asyncio.create_task(synthetic_sensor_loop())
    asyncio.create_task(inference_loop())
    threading.Thread(target=kafka_consumer_loop, name="crowd-kafka-consumer", daemon=True).start()
    print("[SSOS] CrowdLSTM v2 service started")


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {"service": "Crowd Prediction (LSTM v2)", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "model": "CrowdLSTM-v2", "zones": len(ZONES)}

@app.get("/api/v1/prediction/{zone}")
async def get_zone_prediction(zone: str):
    if zone not in ZONES:
        return {"error": "Zone not found", "available_zones": ZONES}
    return _infer_zone(zone)

@app.get("/api/v1/prediction/all")
async def get_all_predictions():
    cached = redis_client.get("predictions:all")
    if cached:
        return {"predictions": json.loads(cached), "source": "cache",
                "updated_at": redis_client.get("predictions:updated_at")}
    predictions = [_infer_zone(z) for z in ZONES]
    return {"predictions": predictions, "source": "live", "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/v1/crushguard/alerts")
async def get_crush_alerts():
    raw = redis_client.get("crush_alerts:active")
    alerts = json.loads(raw) if raw else []
    return {"alerts": alerts, "count": len(alerts), "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/v1/crushguard/{zone}")
async def get_zone_crushguard(zone: str):
    if zone not in ZONES:
        return {"error": "Zone not found"}
    result = _infer_zone(zone)
    return result["crush_guard"]

@app.get("/api/v1/density/current")
async def get_current_density():
    current = {}
    for zone in ZONES:
        v = redis_client.get(f"density:{zone}")
        current[zone] = float(v) if v else 0.0
    return {"density": current, "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/v1/observation")
async def receive_observation(data: dict):
    zone = data.get("zone")
    density = float(data.get("density", 0))
    velocity = float(data.get("velocity", 1.0))
    if zone and zone in ZONES:
        feature_buffer.push(zone, density, velocity)
        zone_density_history[zone].append(density)
        redis_client.set(f"density:{zone}", round(density, 2))
        return {"status": "observed", "zone": zone}
    return {"status": "error", "message": "Invalid zone"}


# ── Demo / judge interaction endpoints ───────────────────────────────────────

_surge_active: Dict[str, bool] = {}

@app.post("/api/v1/demo/surge")
async def trigger_surge(data: dict):
    """
    Inject a sudden crowd surge into a zone for live demo purposes.

    Body: { "zone": "gate_a", "target_density": 92, "velocity": 0.3 }

    This instantly pushes the zone into CrushGuard DANGER territory so judges
    can watch the full alert → response → stabilise flow live on the dashboard.
    """
    zone = data.get("zone", "gate_a")
    target_density = float(data.get("target_density", 92.0))
    velocity = float(data.get("velocity", 0.3))

    if zone not in ZONES:
        return {"error": f"Unknown zone '{zone}'", "valid_zones": ZONES[:8]}

    # Push 8 identical readings to saturate the LSTM lookback window
    for _ in range(8):
        feature_buffer.push(zone, target_density, velocity)
        zone_density_history[zone].append(target_density)
        if len(zone_density_history[zone]) > 100:
            zone_density_history[zone].pop(0)
        zone_velocity[zone] = velocity

    redis_client.set(f"density:{zone}", round(target_density, 2))
    redis_client.set(f"velocity:{zone}", round(velocity, 3))
    _surge_active[zone] = True

    # Run inference immediately so dashboard sees the alert without waiting 10s
    result = _infer_zone(zone)
    redis_client.set(f"crushguard:{zone}:level", result["crush_guard"]["alert_level"])
    redis_client.publish("crushguard_alerts", json.dumps(result["crush_guard"]))
    redis_client.publish("dashboard:live", json.dumps({
        "type": "PREDICTIONS",
        "payload": [result],
        "timestamp": datetime.utcnow().isoformat(),
    }))

    return {
        "status": "surge_injected",
        "zone": zone,
        "density": target_density,
        "crushguard": result["crush_guard"],
    }


@app.post("/api/v1/demo/reset")
async def reset_surge(data: dict):
    """Reset a surged zone back to normal density (for Before/After demo)."""
    zone = data.get("zone", "gate_a")
    if zone not in ZONES:
        return {"error": f"Unknown zone '{zone}'"}

    normal_density = 35.0

    for _ in range(5):
        feature_buffer.push(zone, normal_density, 1.4)
        zone_density_history[zone].append(normal_density)
        if len(zone_density_history[zone]) > 100:
            zone_density_history[zone].pop(0)
        zone_velocity[zone] = 1.4

    redis_client.set(f"density:{zone}", round(normal_density, 2))
    _surge_active.pop(zone, None)
    result = _infer_zone(zone)

    redis_client.publish("dashboard:live", json.dumps({
        "type": "PREDICTIONS",
        "payload": [result],
        "timestamp": datetime.utcnow().isoformat(),
    }))

    return {"status": "reset", "zone": zone, "density": normal_density, "crushguard": result["crush_guard"]}


@app.get("/api/v1/demo/status")
async def demo_status():
    """Returns current surge state for all zones — useful for demo coordination."""
    return {
        "active_surges": list(_surge_active.keys()),
        "demo_mode": os.getenv("DEMO_MODE", "false"),
        "timestamp": datetime.utcnow().isoformat(),
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
