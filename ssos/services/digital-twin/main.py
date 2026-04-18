import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, List
from fastapi import FastAPI
import redis

app = FastAPI(title="Digital Twin Engine", version="1.0.0")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("ssos.digital_twin")

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

class StadiumAgent:
    def __init__(self, agent_id: str, start_zone: str):
        self.id = agent_id
        self.current_zone = start_zone
        self.target_zone = None
        self.velocity = 1.0
        self.state = "moving"
        self.last_update = datetime.utcnow()

class StadiumDigitalTwin:
    def __init__(self):
        self.agents = {}
        self.zones = self._initialize_zones()
        self.simulation_running = False
        
    def _initialize_zones(self) -> Dict:
        return {
            "gate_a": {"capacity": 500, "current_load": 0, "type": "entry"},
            "gate_b": {"capacity": 500, "current_load": 0, "type": "entry"},
            "gate_c": {"capacity": 500, "current_load": 0, "type": "entry"},
            "concourse_a": {"capacity": 1000, "current_load": 0, "type": "circulation"},
            "concourse_b": {"capacity": 1000, "current_load": 0, "type": "circulation"},
            "concourse_c": {"capacity": 800, "current_load": 0, "type": "circulation"},
            "stand_north": {"capacity": 5000, "current_load": 0, "type": "seating"},
            "stand_south": {"capacity": 5000, "current_load": 0, "type": "seating"},
            "food_court_1": {"capacity": 300, "current_load": 0, "type": "amenity"},
            "food_court_2": {"capacity": 300, "current_load": 0, "type": "amenity"},
            "restroom_1": {"capacity": 100, "current_load": 0, "type": "amenity"},
            "exit_north": {"capacity": 800, "current_load": 0, "type": "exit"},
            "exit_south": {"capacity": 800, "current_load": 0, "type": "exit"},
        }
    
    def _get_real_density(self, zone: str) -> float:
        """Fetch real density from Redis crowd-prediction service."""
        return float(redis_client.get(f"density:{zone}") or 35.0)

    def _get_real_velocity(self, zone: str) -> float:
        """Fetch real velocity from Redis crowd-prediction service."""
        return float(redis_client.get(f"velocity:{zone}") or 1.0)

    def spawn_agents(self, count: int):
        entry_points = ["gate_a", "gate_b", "gate_c"]
        cycle = 0
        for i in range(count):
            start_zone = entry_points[i % len(entry_points)]
            agent = StadiumAgent(f"agent_{i}", start_zone)
            self.agents[agent.id] = agent
            self.zones[start_zone]["current_load"] += 1
            cycle += 1
            
    def simulate_movement(self):
        for agent in self.agents.values():
            if agent.state == "moving":
                zone = agent.current_zone
                current_load = self.zones[zone]["current_load"]
                capacity = self.zones[zone]["capacity"]
                density = self._get_real_density(zone)
                
                if density > 70:
                    agent.velocity = max(0.5, agent.velocity - 0.2)
                else:
                    agent.velocity = min(2.0, agent.velocity + 0.1)
                
                density_for_zone = self._get_real_density(zone)
                should_move = density_for_zone < 80 and capacity > current_load
                
                if should_move:
                    possible_zones = self._get_adjacent_zones(zone)
                    if possible_zones and len(possible_zones) > 0:
                        new_zone = possible_zones[len(self.agents) % len(possible_zones)]
                        self.zones[zone]["current_load"] -= 1
                        agent.current_zone = new_zone
                        self.zones[new_zone]["current_load"] += 1
                        
    def _get_adjacent_zones(self, zone: str) -> List[str]:
        adjacency = {
            "gate_a": ["concourse_a"],
            "gate_b": ["concourse_a", "concourse_b"],
            "gate_c": ["concourse_b"],
            "concourse_a": ["gate_a", "gate_b", "stand_north", "food_court_1", "restroom_1"],
            "concourse_b": ["gate_c", "concourse_a", "stand_south", "food_court_1"],
            "concourse_c": ["concourse_a", "food_court_2"],
            "stand_north": ["concourse_a", "exit_north"],
            "stand_south": ["concourse_b", "exit_south"],
            "food_court_1": ["concourse_a", "concourse_b"],
            "food_court_2": ["concourse_c"],
            "restroom_1": ["concourse_a"],
            "exit_north": ["stand_north"],
            "exit_south": ["stand_south"],
        }
        return adjacency.get(zone, [])
        
    def get_simulation_state(self) -> Dict:
        zone_states = {}
        for zone_id, zone_data in self.zones.items():
            zone_states[zone_id] = {
                "load": zone_data["current_load"],
                "capacity": zone_data["capacity"],
                "density": round((zone_data["current_load"] / zone_data["capacity"]) * 100, 1),
                "type": zone_data["type"]
            }
            
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_agents": len(self.agents),
            "zones": zone_states,
            "simulation_time": datetime.utcnow().isoformat()
        }
        
    def run_what_if_scenario(self, scenario: Dict) -> Dict:
        test_twin = StadiumDigitalTwin()
        test_twin.zones = json.loads(json.dumps(self.zones))
        
        if scenario.get("action") == "close_gate":
            gate = scenario.get("gate")
            test_twin.zones[gate]["capacity"] = 0
            
        elif scenario.get("action") == "increase_capacity":
            zone = scenario.get("zone")
            test_twin.zones[zone]["capacity"] = int(test_twin.zones[zone]["capacity"] * 1.5)
            
        return test_twin.get_simulation_state()

digital_twin = StadiumDigitalTwin()
digital_twin.spawn_agents(1000)

async def simulation_loop():
    while True:
        digital_twin.simulate_movement()
        state = digital_twin.get_simulation_state()
        redis_client.set("digital_twin:state", json.dumps(state))
        await asyncio.sleep(2)

@app.on_event("startup")
async def startup():
    asyncio.create_task(simulation_loop())
    redis_client.set("digital_twin:status", "running")
    logger.info("Digital twin started with %s agents", len(digital_twin.agents))

@app.get("/")
async def root():
    return {"service": "Digital Twin Engine", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "agents": len(digital_twin.agents)}

@app.get("/api/v1/twin/state")
async def get_state():
    return digital_twin.get_simulation_state()

@app.get("/api/v1/twin/zones")
async def get_zones():
    return {"zones": list(digital_twin.zones.keys())}

@app.get("/api/v1/twin/zone/{zone_id}")
async def get_zone_detail(zone_id: str):
    if zone_id not in digital_twin.zones:
        return {"error": "Zone not found"}
    return digital_twin.zones[zone_id]

@app.post("/api/v1/twin/scenario")
async def run_scenario(scenario: Dict):
    result = digital_twin.run_what_if_scenario(scenario)
    return {"scenario_result": result}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8005)
