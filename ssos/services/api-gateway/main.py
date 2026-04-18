from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Set
from datetime import datetime
import redis
import redis.asyncio as aioredis
import json
import os
import asyncio

app = FastAPI(title="SSOS API Gateway", version="2.0.0")

# Active WebSocket connections
_ws_clients: Set[WebSocket] = set()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True,
)

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")

async def _redis_pubsub_broadcaster():
    """
    Subscribe to all Redis channels that produce live events and fan them
    out to every connected WebSocket client.
    Channels: dashboard:live, crushguard_alerts, decision_actions
    """
    async_redis = aioredis.from_url(f"redis://{REDIS_HOST}:6379", decode_responses=True)
    pubsub = async_redis.pubsub()
    await pubsub.subscribe("dashboard:live", "crushguard_alerts", "decision_actions")

    async for message in pubsub.listen():
        if message["type"] != "message":
            continue
        data = message["data"]
        dead = set()
        for ws in list(_ws_clients):
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        _ws_clients.difference_update(dead)

class User(BaseModel):
    id: str
    name: str
    email: str
    ticket_id: str

class Location(BaseModel):
    user_id: str
    zone_id: str
    x: float
    y: float
    timestamp: datetime

class RouteRequest(BaseModel):
    user_id: str
    from_zone: str
    to_zone: str

class EmergencyAlert(BaseModel):
    zone_id: str
    alert_type: str
    severity: int
    message: str

class FoodOrder(BaseModel):
    user_id: str
    vendor_id: str
    items: List[dict]
    location: dict

@app.on_event("startup")
async def startup():
    asyncio.create_task(_redis_pubsub_broadcaster())
    print("[gateway] WebSocket broadcaster started")


@app.websocket("/ws/dashboard")
async def ws_dashboard(websocket: WebSocket):
    """
    WebSocket endpoint for Mission Control dashboard.
    Receives live JSON frames from the Redis pub/sub broadcaster.
    Client can also send {type: 'PING'} to keep the connection alive.
    """
    await websocket.accept()
    _ws_clients.add(websocket)

    # Send an immediate snapshot so the dashboard isn't blank
    try:
        predictions_raw = redis_client.get("predictions:all")
        crush_raw = redis_client.get("crush_alerts:active")
        twin_raw = redis_client.get("digital_twin:state")
        snapshot = {
            "type": "SNAPSHOT",
            "payload": {
                "predictions": json.loads(predictions_raw) if predictions_raw else [],
                "crush_alerts": json.loads(crush_raw) if crush_raw else [],
                "twin_state": json.loads(twin_raw) if twin_raw else {},
            },
            "timestamp": datetime.utcnow().isoformat(),
        }
        await websocket.send_text(json.dumps(snapshot))

        # Keep connection open; client sends PING to signal it's alive
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                if msg:
                    parsed = json.loads(msg)
                    if parsed.get("type") == "PING":
                        await websocket.send_text(json.dumps({"type": "PONG"}))
            except asyncio.TimeoutError:
                await websocket.send_text(json.dumps({"type": "HEARTBEAT",
                                                       "ts": datetime.utcnow().isoformat()}))
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)


@app.get("/")
async def root():
    return {"service": "SSOS API Gateway", "status": "running",
            "ws_clients": len(_ws_clients), "timestamp": datetime.utcnow().isoformat()}

@app.get("/health")
async def health():
    return {"status": "healthy", "redis": redis_client.ping()}

@app.post("/api/v1/users/register")
async def register_user(user: User):
    key = f"user:{user.id}"
    redis_client.hset(key, mapping={
        "name": user.name,
        "email": user.email,
        "ticket_id": user.ticket_id,
        "created_at": datetime.utcnow().isoformat()
    })
    redis_client.sadd("users", user.id)
    return {"status": "registered", "user_id": user.id}

@app.get("/api/v1/users/{user_id}")
async def get_user(user_id: str):
    user_data = redis_client.hgetall(f"user:{user_id}")
    if not user_data:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user_id": user_id, **user_data}

@app.post("/api/v1/location/update")
async def update_location(location: Location):
    key = f"location:{location.user_id}"
    redis_client.hset(key, mapping={
        "zone_id": location.zone_id,
        "x": str(location.x),
        "y": str(location.y),
        "timestamp": location.timestamp.isoformat()
    })
    redis_client.publish("location_updates", json.dumps({
        "user_id": location.user_id,
        "zone_id": location.zone_id,
        "x": location.x,
        "y": location.y,
        "timestamp": location.timestamp.isoformat()
    }))
    return {"status": "updated", "user_id": location.user_id}

@app.get("/api/v1/zones")
async def get_zones():
    zones = redis_client.hgetall("stadium:zones")
    return {"zones": zones}

@app.get("/api/v1/zones/{zone_id}/density")
async def get_zone_density(zone_id: str):
    density = redis_client.get(f"density:{zone_id}")
    if density is None:
        raise HTTPException(status_code=404, detail="Zone density not found")
    return {"zone_id": zone_id, "density": float(density), "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/v1/zones/heatmap")
async def get_heatmap():
    zones = redis_client.keys("density:*")
    heatmap = {}
    for zone_key in zones:
        zone_id = zone_key.replace("density:", "")
        heatmap[zone_id] = float(redis_client.get(zone_key))
    return {"heatmap": heatmap, "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/v1/routing/path")
async def get_route(route_request: RouteRequest):
    route_data = {
        "user_id": route_request.user_id,
        "from": route_request.from_zone,
        "to": route_request.to_zone,
        "requested_at": datetime.utcnow().isoformat()
    }
    redis_client.lpush("routing:requests", json.dumps(route_data))
    redis_client.publish("routing_requests", json.dumps(route_data))
    return {"status": "route_requested", "data": route_data}

@app.get("/api/v1/routing/path/{user_id}")
async def get_user_route(user_id: str):
    route = redis_client.get(f"route:{user_id}")
    if route:
        return json.loads(route)
    return {"status": "no_route", "message": "No active route found"}

@app.post("/api/v1/queue/estimate")
async def get_queue_time(zone_id: str):
    queue_time = redis_client.get(f"queue:{zone_id}")
    if queue_time is None:
        return {"zone_id": zone_id, "estimated_minutes": 5, "confidence": "medium"}
    return {"zone_id": zone_id, "estimated_minutes": float(queue_time), "confidence": "high"}

@app.post("/api/v1/orders/food")
async def create_food_order(order: FoodOrder):
    order_id = f"order:{datetime.utcnow().timestamp()}"
    order_data = {
        "user_id": order.user_id,
        "vendor_id": order.vendor_id,
        "items": json.dumps(order.items),
        "location": json.dumps(order.location),
        "status": "pending",
        "created_at": datetime.utcnow().isoformat()
    }
    redis_client.hset(order_id, mapping=order_data)
    redis_client.publish("food_orders", json.dumps({"order_id": order_id, **order_data}))
    return {"order_id": order_id, "status": "created"}

@app.get("/api/v1/orders/{order_id}")
async def get_order(order_id: str):
    order = redis_client.hgetall(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"order_id": order_id, **order}

@app.post("/api/v1/emergency/alerts")
async def create_emergency_alert(alert: EmergencyAlert):
    alert_id = f"alert:{datetime.utcnow().timestamp()}"
    alert_data = {
        "zone_id": alert.zone_id,
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "message": alert.message,
        "created_at": datetime.utcnow().isoformat()
    }
    redis_client.hset(alert_id, mapping=alert_data)
    redis_client.publish("emergency_alerts", json.dumps({"alert_id": alert_id, **alert_data}))
    return {"alert_id": alert_id, "status": "broadcasted"}

@app.get("/api/v1/emergency/alerts")
async def get_active_alerts():
    alerts = redis_client.keys("alert:*")
    active_alerts = []
    for alert_key in alerts:
        alert = redis_client.hgetall(alert_key)
        if alert:
            active_alerts.append({"alert_id": alert_key, **alert})
    return {"alerts": active_alerts, "count": len(active_alerts)}

@app.get("/api/v1/dashboard/stats")
async def get_dashboard_stats():
    user_count = redis_client.scard("users")
    active_routes = redis_client.keys("route:*")
    return {
        "total_users": user_count,
        "active_routes": len(active_routes),
        "timestamp": datetime.utcnow().isoformat()
    }

@app.post("/api/v1/staff/assign")
async def assign_staff_task(zone_id: str, staff_id: str, task: str):
    task_id = f"task:{datetime.utcnow().timestamp()}"
    task_data = {
        "zone_id": zone_id,
        "staff_id": staff_id,
        "task": task,
        "status": "assigned",
        "created_at": datetime.utcnow().isoformat()
    }
    redis_client.hset(task_id, mapping=task_data)
    redis_client.publish("staff_tasks", json.dumps({"task_id": task_id, **task_data}))
    return {"task_id": task_id, "status": "assigned"}

@app.get("/api/v1/staff/tasks/{staff_id}")
async def get_staff_tasks(staff_id: str):
    tasks = redis_client.keys(f"task:*")
    staff_tasks = []
    for task_key in tasks:
        task = redis_client.hgetall(task_key)
        if task and task.get("staff_id") == staff_id:
            staff_tasks.append({"task_id": task_key, **task})
    return {"tasks": staff_tasks}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)