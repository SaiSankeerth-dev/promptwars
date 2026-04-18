import os
import json
import time
import threading
import logging
import redis
import numpy as np
from datetime import datetime
from typing import Dict, List
from kafka import KafkaProducer

app_host = os.getenv("KAFKA_BROKERS", "localhost:29092").split(",")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("ssos.edge_node")

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

class EdgeNodeSimulator:
    def __init__(self, node_id: str, zone_ids: List[str]):
        self.node_id = node_id
        self.zone_ids = zone_ids
        self.producer = None
        self.running = False
        
    def connect_kafka(self):
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=app_host,
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                acks='all'
            )
            logger.info("[%s] Connected to Kafka", self.node_id)
        except Exception as e:
            logger.warning("[%s] Kafka connection failed: %s", self.node_id, e)
            
    def _fetch_from_redis(self, zone_id: str) -> Dict:
        """Fetch real density/velocity from Redis crowd-prediction service."""
        density = float(redis_client.get(f"density:{zone_id}") or 50.0)
        velocity = float(redis_client.get(f"velocity:{zone_id}") or 1.0)
        return density, velocity

    def simulate_camera_frame(self, zone_id: str) -> Dict:
        density, velocity = self._fetch_from_redis(zone_id)
        person_count = int((density / 100) * 200)
        
        return {
            "node_id": self.node_id,
            "zone": zone_id,
            "timestamp": datetime.utcnow().isoformat(),
            "frame_id": f"frame_{int(time.time() * 1000) % 10000}",
            "detections": {
                "person_count": person_count,
                "density": round(density, 2),
                "avg_velocity": round(velocity, 2),
                "motion_pattern": "standing" if density > 70 else "walking",
            },
            "anonymized": True,
            "processing_time_ms": 15
        }
        
    def simulate_iot_sensor(self, zone_id: str) -> Dict:
        density, _ = self._fetch_from_redis(zone_id)
        occupancy = int((density / 100) * self.zone_capacity(zone_id))
        
        return {
            "node_id": self.node_id,
            "zone": zone_id,
            "timestamp": datetime.utcnow().isoformat(),
            "sensor_type": "people_counter",
            "readings": {
                "entry_count": max(0, int((density / 100) * 20)),
                "exit_count": max(0, int((density / 100) * 10)),
                "current_occupancy": occupancy,
                "temperature": 22.0 + (density / 100) * 4,
                "humidity": 55
            }
        }
    
    def zone_capacity(self, zone_id: str) -> int:
        capacities = {
            "gate_a": 3000, "gate_b": 3000, "gate_c": 3000,
            "concourse_a": 2000, "concourse_b": 2000, "concourse_c": 1500,
            "stand_north": 25000, "stand_south": 25000,
            "food_court_1": 300, "food_court_2": 300,
            "restroom_1": 100, "restroom_2": 100,
            "exit_north": 5000, "exit_south": 5000,
        }
        return capacities.get(zone_id, 500)
        
    def simulate_ble_beacon(self, zone_id: str) -> Dict:
        density, _ = self._fetch_from_redis(zone_id)
        devices = int((density / 100) * 30)
        
        return {
            "node_id": self.node_id,
            "zone": zone_id,
            "timestamp": datetime.utcnow().isoformat(),
            "beacon_type": "ble_anchor",
            "devices_detected": devices,
            "avg_rssi": -60
        }
        
    def run(self):
        self.connect_kafka()
        self.running = True
        
        logger.info("[%s] Edge node started for zones: %s", self.node_id, self.zone_ids)
        
        iteration = 0
        while self.running:
            for zone_id in self.zone_ids:
                camera_data = self.simulate_camera_frame(zone_id)
                iot_data = self.simulate_iot_sensor(zone_id)
                ble_data = self.simulate_ble_beacon(zone_id)
                
                if self.producer:
                    try:
                        self.producer.send('crowd_observations', camera_data)
                        self.producer.send('iot_sensors', iot_data)
                        self.producer.send('ble_devices', ble_data)
                        self.producer.flush()
                    except Exception as e:
                        logger.warning("[%s] Send error: %s", self.node_id, e)
                        
            iteration += 1
            if iteration % 10 == 0:
                logger.info("[%s] Sent data for %s zones (%s cycles)", self.node_id, len(self.zone_ids), iteration)
                
            time.sleep(3)
            
    def stop(self):
        self.running = False
        if self.producer:
            self.producer.close()
            
class CrowdDensityModel:
    def __init__(self):
        self.model_loaded = True
        
    def detect_persons(self, frame_data: Dict) -> int:
        return frame_data.get("detections", {}).get("person_count", 0)
        
    def calculate_density(self, person_count: int, zone_area_sqm: int) -> float:
        return (person_count / zone_area_sqm) * 100
        
    def get_density_from_redis(self, zone: str) -> float:
        """Fetch real density from Redis crowd-prediction service."""
        return float(redis_client.get(f"density:{zone}") or 50.0)
    
    def get_velocity_from_redis(self, zone: str) -> float:
        """Fetch real velocity from Redis crowd-prediction service."""
        return float(redis_client.get(f"velocity:{zone}") or 1.0)
        
    def detect_anomaly(self, frame_data: Dict, zone: str) -> Dict:
        density = self.get_density_from_redis(zone)
        velocity = self.get_velocity_from_redis(zone)
        
        if velocity > 3.0:
            return {"type": "high_velocity", "severity": "medium", "details": "Unusually high movement detected", "density": density}
        if density > 80:
            return {"type": "crush_warning", "severity": "high", "details": "High density detected in zone", "density": density}
            
        return None

class DataAnonymizer:
    def anonymize(self, data: Dict) -> Dict:
        anonymized = data.copy()
        if "user_id" in anonymized:
            anonymized["user_id"] = self._hash_id(anonymized["user_id"])
        return anonymized
        
    def _hash_id(self, original_id: str) -> str:
        return f"anon_{hash(original_id) % 100000}"

logger.info("SSOS Edge Node - Reading Real Data from Redis")

edge_nodes = [
    EdgeNodeSimulator("edge_node_1", ["gate_a", "gate_b", "concourse_a"]),
    EdgeNodeSimulator("edge_node_2", ["gate_c", "concourse_b", "stand_north"]),
    EdgeNodeSimulator("edge_node_3", ["food_court_1", "food_court_2", "concourse_c"]),
]

threads = []

try:
    for node in edge_nodes:
        thread = threading.Thread(target=node.run, name=node.node_id, daemon=True)
        thread.start()
        threads.append(thread)

    while True:
        time.sleep(1)
except KeyboardInterrupt:
    logger.info("Stopping all edge simulators")
finally:
    for node in edge_nodes:
        node.stop()
