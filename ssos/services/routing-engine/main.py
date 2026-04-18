import os
import json
import heapq
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from fastapi import FastAPI
import redis

app = FastAPI(title="Smart Routing Engine", version="1.0.0")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO").upper())
logger = logging.getLogger("ssos.routing_engine")

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

@dataclass(order=True)
class PriorityQueueItem:
    priority: float
    node: str = field(compare=False)
    path: List[str] = field(compare=False)

class StadiumGraph:
    def __init__(self):
        self.nodes = set()
        self.edges = {}
        self.capacities = {}
        self.current_loads = {}
        
    def add_node(self, node: str):
        self.nodes.add(node)
        if node not in self.edges:
            self.edges[node] = []
            self.current_loads[node] = 0
            
    def add_edge(self, from_node: str, to_node: str, distance: float, capacity: int):
        self.add_node(from_node)
        self.add_node(to_node)
        self.edges[from_node].append({"to": to_node, "distance": distance, "capacity": capacity})
        self.capacities[f"{from_node}->{to_node}"] = capacity
        
    def get_weight(self, from_node: str, to_node: str) -> float:
        for edge in self.edges.get(from_node, []):
            if edge["to"] == to_node:
                base_weight = edge["distance"]
                load = self.current_loads.get(from_node, 0)
                capacity = edge.get("capacity", 100)
                load_factor = 1 + (load / capacity) * 2
                return base_weight * load_factor
        return float('inf')
    
    def update_load(self, node: str, load_delta: int):
        self.current_loads[node] = self.current_loads.get(node, 0) + load_delta
        self.current_loads[node] = max(0, self.current_loads[node])


# Approximate 2-D coordinates for each zone (metres from SW corner of venue).
# Used by A* heuristic for an admissible, real distance estimate.
ZONE_COORDS_M: Dict[str, Tuple[float, float]] = {
    "gate_a":       (20,  10),  "gate_b":  (90,  10),  "gate_c": (160, 10),
    "gate_d":       (230, 10),  "gate_e":  (300, 10),
    "concourse_a":  (40,  60),  "concourse_b": (120, 60),
    "concourse_c":  (200, 60),  "concourse_d": (280, 60),
    "stand_north":  (160, 120), "stand_south": (160, 300),
    "stand_east":   (300, 210), "stand_west":  (20,  210),
    "restroom_1":   (40,  160), "restroom_2":  (120, 160),
    "restroom_3":   (200, 160), "restroom_4":  (280, 160),
    "food_court_1": (90,  210), "food_court_2": (230, 210),
    "vendor_row_1": (80,  180), "vendor_row_2": (240, 180),
    "exit_north":   (90,  380), "exit_south":  (230, 380),
    "exit_east":    (340, 210), "exit_west":   (0,   210),
}

def _euclidean_heuristic(a: str, b: str) -> float:
    """Admissible A* heuristic: straight-line distance between zone centres."""
    ax, ay = ZONE_COORDS_M.get(a, (0, 0))
    bx, by = ZONE_COORDS_M.get(b, (0, 0))
    return ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5


class SmartRoutingEngine:
    def __init__(self):
        self.graph = self._build_stadium_graph()
        self.active_routes = {}
        
    def _build_stadium_graph(self) -> StadiumGraph:
        graph = StadiumGraph()
        
        connections = [
            ("gate_a", "concourse_a", 50, 500),
            ("gate_b", "concourse_a", 40, 500),
            ("gate_b", "concourse_b", 60, 400),
            ("gate_c", "concourse_b", 45, 500),
            ("gate_d", "concourse_c", 50, 400),
            ("gate_e", "concourse_c", 55, 500),
            ("gate_e", "concourse_d", 40, 400),
            
            ("concourse_a", "stand_north", 80, 1000),
            ("concourse_a", "concourse_b", 30, 600),
            ("concourse_b", "stand_south", 75, 1000),
            ("concourse_b", "concourse_c", 35, 600),
            ("concourse_c", "stand_east", 70, 1000),
            ("concourse_c", "concourse_d", 25, 600),
            ("concourse_d", "stand_west", 70, 1000),
            
            ("concourse_a", "food_court_1", 40, 300),
            ("concourse_b", "food_court_1", 45, 300),
            ("concourse_c", "food_court_2", 40, 300),
            ("concourse_d", "food_court_2", 35, 300),
            
            ("concourse_a", "restroom_1", 25, 200),
            ("concourse_b", "restroom_2", 30, 200),
            ("concourse_c", "restroom_3", 25, 200),
            ("concourse_d", "restroom_4", 30, 200),
            
            ("stand_north", "exit_north", 60, 800),
            ("stand_south", "exit_south", 60, 800),
            ("stand_east", "exit_east", 55, 800),
            ("stand_west", "exit_west", 55, 800),
            
            ("concourse_a", "exit_north", 70, 600),
            ("concourse_b", "exit_south", 70, 600),
            ("concourse_c", "exit_east", 65, 600),
            ("concourse_d", "exit_west", 65, 600),
            
            ("vendor_row_1", "concourse_a", 20, 400),
            ("vendor_row_1", "concourse_b", 25, 400),
            ("vendor_row_2", "concourse_c", 20, 400),
            ("vendor_row_2", "concourse_d", 25, 400),
        ]
        
        for from_node, to_node, distance, capacity in connections:
            graph.add_edge(from_node, to_node, distance, capacity)
            graph.add_edge(to_node, from_node, distance, capacity)
            
        return graph
    
    def dijkstra(self, start: str, end: str, avoid_zones: List[str] = None) -> Optional[Dict]:
        if start not in self.graph.nodes or end not in self.graph.nodes:
            return None
            
        avoid = set(avoid_zones) if avoid_zones else set()
        
        distances = {node: float('inf') for node in self.graph.nodes}
        distances[start] = 0
        predecessors = {node: None for node in self.graph.nodes}
        
        pq = [(0, start, [start])]
        visited = set()
        
        while pq:
            current_dist, current_node, path = heapq.heappop(pq)
            
            if current_node in visited:
                continue
            visited.add(current_node)
            
            if current_node == end:
                return {
                    "path": path,
                    "distance": current_dist,
                    "eta_minutes": round(current_dist / 60, 1),
                    "waypoints": len(path),
                    "avoid_zones": list(avoid)
                }
            
            for edge in self.graph.edges.get(current_node, []):
                neighbor = edge["to"]
                
                if neighbor in avoid or neighbor in visited:
                    continue
                    
                weight = self.graph.get_weight(current_node, neighbor)
                new_dist = current_dist + weight
                
                if new_dist < distances[neighbor]:
                    distances[neighbor] = new_dist
                    predecessors[neighbor] = current_node
                    new_path = path + [neighbor]
                    heapq.heappush(pq, (new_dist, neighbor, new_path))
        
        return None
    
    def a_star(self, start: str, end: str, avoid_zones: List[str] = None) -> Optional[Dict]:
        avoid = set(avoid_zones) if avoid_zones else set()

        if start not in self.graph.nodes or end not in self.graph.nodes:
            return None

        g_scores = {start: 0}
        f_scores = {start: _euclidean_heuristic(start, end)}
        predecessors = {start: None}
        
        open_set = [(f_scores[start], start, [start])]
        closed_set = set()
        
        while open_set:
            _, current, path = heapq.heappop(open_set)
            
            if current in closed_set:
                continue
            closed_set.add(current)
            
            if current == end:
                total_dist = g_scores[current]
                return {
                    "path": path,
                    "distance": total_dist,
                    "eta_minutes": round(total_dist / 60, 1),
                    "algorithm": "A*",
                    "waypoints": len(path),
                    "avoid_zones": list(avoid)
                }
            
            for edge in self.graph.edges.get(current, []):
                neighbor = edge["to"]
                
                if neighbor in avoid or neighbor in closed_set:
                    continue
                    
                tentative_g = g_scores[current] + self.graph.get_weight(current, neighbor)
                
                if neighbor not in g_scores or tentative_g < g_scores[neighbor]:
                    g_scores[neighbor] = tentative_g
                    f_scores[neighbor] = tentative_g + _euclidean_heuristic(neighbor, end)
                    predecessors[neighbor] = current
                    new_path = path + [neighbor]
                    heapq.heappush(open_set, (f_scores[neighbor], neighbor, new_path))
        
        return None
    
    def find_best_route(self, from_zone: str, to_zone: str, avoid_zones: List[str] = None) -> Dict:
        route = self.dijkstra(from_zone, to_zone, avoid_zones)
        
        if not route:
            route = self.a_star(from_zone, to_zone, avoid_zones)
            
        if route:
            self.active_routes[f"{from_zone}->{to_zone}"] = {
                "timestamp": datetime.utcnow().isoformat(),
                "path": route["path"]
            }
            self._update_graph_loads(route["path"])
            
        return route
    
    def _update_graph_loads(self, path: List[str]):
        for node in path:
            self.graph.update_load(node, 1)
            
    def get_alternative_routes(self, from_zone: str, to_zone: str, alternatives: int = 3) -> List[Dict]:
        routes = []
        
        primary_route = self.find_best_route(from_zone, to_zone)
        if primary_route:
            routes.append({**primary_route, "rank": 1})
            
        all_nodes = list(self.graph.nodes)
        
        for i in range(alternatives - 1):
            avoid = [r["path"][len(r["path"])//2] if len(r["path"]) > 2 else r["path"][0] 
                     for r in routes if "path" in r]
            
            alt_route = self.find_best_route(from_zone, to_zone, avoid[:i+1])
            if alt_route:
                routes.append({**alt_route, "rank": i + 2})
                
        return routes
    
    def optimize_for_load_balancing(self, routes: List[Dict]) -> List[Dict]:
        load_balanced = []
        
        for route in routes:
            path_loads = []
            for node in route.get("path", []):
                load = self.graph.current_loads.get(node, 0)
                path_loads.append(load)
            
            avg_load = sum(path_loads) / len(path_loads) if path_loads else 0
            route["avg_path_load"] = avg_load
            
            load_balanced.append(route)
            
        return sorted(load_balanced, key=lambda x: x.get("avg_path_load", float('inf')))

routing_engine = SmartRoutingEngine()

@app.on_event("startup")
async def startup():
    for node in routing_engine.graph.nodes:
        redis_client.hset("routing:nodes", node, json.dumps({
            "name": node.replace("_", " ").title(),
            "type": "gate" if "gate" in node else "concourse" if "concourse" in node 
                   else "stand" if "stand" in node else "exit" if "exit" in node 
                   else "facility"
        }))
    logger.info("Routing engine initialized with %s nodes", len(routing_engine.graph.nodes))

@app.get("/")
async def root():
    return {"service": "Smart Routing Engine", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/api/v1/route/{from_zone}/{to_zone}")
async def get_route(from_zone: str, to_zone: str, avoid: str = None):
    avoid_zones = avoid.split(",") if avoid else None
    route = routing_engine.find_best_route(from_zone, to_zone, avoid_zones)
    
    if route:
        route["from"] = from_zone
        route["to"] = to_zone
        return route
    
    return {"error": "No route found", "from": from_zone, "to": to_zone}

@app.get("/api/v1/route/alternatives/{from_zone}/{to_zone}")
async def get_alternative_routes(from_zone: str, to_zone: str, count: int = 3):
    routes = routing_engine.get_alternative_routes(from_zone, to_zone, count)
    load_balanced = routing_engine.optimize_for_load_balancing(routes)
    
    return {
        "from": from_zone,
        "to": to_zone,
        "routes": load_balanced,
        "count": len(routes)
    }

@app.get("/api/v1/nodes")
async def get_all_nodes():
    return {
        "nodes": list(routing_engine.graph.nodes),
        "count": len(routing_engine.graph.nodes)
    }

@app.get("/api/v1/loads")
async def get_node_loads():
    loads = {}
    for node, load in routing_engine.graph.current_loads.items():
        loads[node] = load
    return {"loads": loads, "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/v1/route/optimize")
async def optimize_multiple_routes(routes: List[Dict]):
    return routing_engine.optimize_for_load_balancing(routes)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
