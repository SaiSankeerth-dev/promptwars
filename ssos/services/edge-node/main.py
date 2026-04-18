import os
import json
import time
import random
import numpy as np
from datetime import datetime
from typing import Dict, List
from kafka import KafkaProducer

app_host = os.getenv("KAFKA_BROKERS", "localhost:29092").split(",")

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
            print(f"[{self.node_id}] Connected to Kafka")
        except Exception as e:
            print(f"[{self.node_id}] Kafka connection failed: {e}")
            
    def simulate_camera_frame(self, zone_id: str) -> Dict:
        base_people = random.randint(10, 50)
        density = random.uniform(20, 80)
        
        return {
            "node_id": self.node_id,
            "zone": zone_id,
            "timestamp": datetime.utcnow().isoformat(),
            "frame_id": f"frame_{random.randint(1000, 9999)}",
            "detections": {
                "person_count": base_people,
                "density": round(density, 2),
                "avg_velocity": round(random.uniform(0.5, 2.0), 2),
                "motion_pattern": random.choice(["walking", "standing", "running"]),
            },
            "anonymized": True,
            "processing_time_ms": random.randint(10, 50)
        }
        
    def simulate_iot_sensor(self, zone_id: str) -> Dict:
        return {
            "node_id": self.node_id,
            "zone": zone_id,
            "timestamp": datetime.utcnow().isoformat(),
            "sensor_type": "people_counter",
            "readings": {
                "entry_count": random.randint(0, 20),
                "exit_count": random.randint(0, 20),
                "current_occupancy": random.randint(50, 500),
                "temperature": round(random.uniform(20, 28), 1),
                "humidity": random.randint(40, 70)
            }
        }
        
    def simulate_ble_beacon(self, zone_id: str) -> Dict:
        devices = random.randint(5, 30)
        return {
            "node_id": self.node_id,
            "zone": zone_id,
            "timestamp": datetime.utcnow().isoformat(),
            "beacon_type": "ble_anchor",
            "devices_detected": devices,
            "avg_rssi": random.randint(-70, -50)
        }
        
    def run(self):
        self.connect_kafka()
        self.running = True
        
        print(f"[{self.node_id}] Edge node started for zones: {self.zone_ids}")
        
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
                        print(f"[{self.node_id}] Send error: {e}")
                        
            iteration += 1
            if iteration % 10 == 0:
                print(f"[{self.node_id}] Sent data for {len(self.zone_ids)} zones ({iteration} cycles)")
                
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
        
    def detect_anomaly(self, frame_data: Dict) -> Dict:
        velocity = frame_data.get("detections", {}).get("avg_velocity", 0)
        
        if velocity > 3.0:
            return {"type": "high_velocity", "severity": "medium", "details": "Unusually high movement detected"}
        if frame_data.get("detections", {}).get("motion_pattern") == "running":
            return {"type": "running_detected", "severity": "high", "details": "Running behavior detected"}
            
        return None

class DataAnonymizer:
    def anonymize(self, data: Dict) -> Dict:
        anonymized = data.copy()
        if "user_id" in anonymized:
            anonymized["user_id"] = self._hash_id(anonymized["user_id"])
        return anonymized
        
    def _hash_id(self, original_id: str) -> str:
        return f"anon_{hash(original_id) % 100000}"

print("=" * 50)
print("SSOS Edge Node Simulator")
print("=" * 50)
print()

edge_nodes = [
    EdgeNodeSimulator("edge_node_1", ["gate_a", "gate_b", "concourse_a"]),
    EdgeNodeSimulator("edge_node_2", ["gate_c", "concourse_b", "stand_north"]),
    EdgeNodeSimulator("edge_node_3", ["food_court_1", "food_court_2", "concourse_c"]),
]

for node in edge_nodes:
    try:
        node.run()
    except KeyboardInterrupt:
        print(f"\n[{node.node_id}] Stopping...")
        node.stop()
    except Exception as e:
        print(f"[{node.node_id}] Error: {e}")
        node.stop()