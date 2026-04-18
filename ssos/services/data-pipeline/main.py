import os
import json
import asyncio
from datetime import datetime
from typing import Dict, List
from fastapi import FastAPI
import redis
from kafka import KafkaConsumer, KafkaProducer
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

app = FastAPI(title="Data Pipeline", version="1.0.0")

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
DATABASE_URL = f"postgresql://ssos:ssos_password@{POSTGRES_HOST}:5432/ssos_db"

engine = create_engine(DATABASE_URL)
Base = declarative_base()

class CrowdObservation(Base):
    __tablename__ = 'crowd_observations'
    id = Column(Integer, primary_key=True, autoincrement=True)
    zone_id = Column(String(100))
    density = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

class UserLocation(Base):
    __tablename__ = 'user_locations'
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(100))
    zone_id = Column(String(100))
    x = Column(Float)
    y = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)

class FoodOrder(Base):
    __tablename__ = 'food_orders'
    id = Column(Integer, primary_key=True, autoincrement=True)
    order_id = Column(String(100))
    user_id = Column(String(100))
    vendor_id = Column(String(100))
    items = Column(Text)
    status = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)

class EmergencyAlert(Base):
    __tablename__ = 'emergency_alerts'
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(100))
    zone_id = Column(String(100))
    alert_type = Column(String(100))
    severity = Column(Integer)
    message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:29092").split(",")

class DataPipeline:
    def __init__(self):
        self.stats = {
            "crowd_observations": 0,
            "location_updates": 0,
            "food_orders": 0,
            "emergency_alerts": 0,
            "errors": 0
        }
        self.running = False
        
    async def consume_crowd_observations(self):
        while self.running:
            try:
                consumer = KafkaConsumer(
                    'crowd_observations',
                    bootstrap_servers=KAFKA_BROKERS,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    auto_offset_reset='latest',
                    group_id='data-pipeline-crowd'
                )
                
                for message in consumer:
                    data = message.value
                    session = Session()
                    try:
                        obs = CrowdObservation(
                            zone_id=data.get("zone"),
                            density=data.get("density", 0),
                            timestamp=datetime.utcnow()
                        )
                        session.add(obs)
                        session.commit()
                        self.stats["crowd_observations"] += 1
                    except Exception as e:
                        self.stats["errors"] += 1
                        session.rollback()
                    finally:
                        session.close()
                        
            except Exception as e:
                await asyncio.sleep(5)
                
    async def consume_location_updates(self):
        while self.running:
            try:
                consumer = KafkaConsumer(
                    'location_updates',
                    bootstrap_servers=KAFKA_BROKERS,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    auto_offset_reset='latest',
                    group_id='data-pipeline-locations'
                )
                
                for message in consumer:
                    data = message.value
                    session = Session()
                    try:
                        loc = UserLocation(
                            user_id=data.get("user_id"),
                            zone_id=data.get("zone_id"),
                            x=data.get("x", 0),
                            y=data.get("y", 0),
                            timestamp=datetime.utcnow()
                        )
                        session.add(loc)
                        session.commit()
                        self.stats["location_updates"] += 1
                    except Exception as e:
                        self.stats["errors"] += 1
                        session.rollback()
                    finally:
                        session.close()
                        
            except Exception as e:
                await asyncio.sleep(5)
                
    async def consume_food_orders(self):
        while self.running:
            try:
                consumer = KafkaConsumer(
                    'food_orders',
                    bootstrap_servers=KAFKA_BROKERS,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    auto_offset_reset='latest',
                    group_id='data-pipeline-orders'
                )
                
                for message in consumer:
                    data = message.value
                    session = Session()
                    try:
                        order = FoodOrder(
                            order_id=data.get("order_id"),
                            user_id=data.get("user_id"),
                            vendor_id=data.get("vendor_id"),
                            items=data.get("items"),
                            status=data.get("status", "pending"),
                            created_at=datetime.utcnow()
                        )
                        session.add(order)
                        session.commit()
                        self.stats["food_orders"] += 1
                    except Exception as e:
                        self.stats["errors"] += 1
                        session.rollback()
                    finally:
                        session.close()
                        
            except Exception as e:
                await asyncio.sleep(5)
                
    async def consume_emergency_alerts(self):
        while self.running:
            try:
                consumer = KafkaConsumer(
                    'emergency_alerts',
                    bootstrap_servers=KAFKA_BROKERS,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    auto_offset_reset='latest',
                    group_id='data-pipeline-emergency'
                )
                
                for message in consumer:
                    data = message.value
                    session = Session()
                    try:
                        alert = EmergencyAlert(
                            alert_id=data.get("alert_id"),
                            zone_id=data.get("zone_id"),
                            alert_type=data.get("alert_type"),
                            severity=data.get("severity", 0),
                            message=data.get("message"),
                            created_at=datetime.utcnow()
                        )
                        session.add(alert)
                        session.commit()
                        self.stats["emergency_alerts"] += 1
                    except Exception as e:
                        self.stats["errors"] += 1
                        session.rollback()
                    finally:
                        session.close()
                        
            except Exception as e:
                await asyncio.sleep(5)
                
    async def start(self):
        self.running = True
        asyncio.create_task(self.consume_crowd_observations())
        asyncio.create_task(self.consume_location_updates())
        asyncio.create_task(self.consume_food_orders())
        asyncio.create_task(self.consume_emergency_alerts())
        
    def stop(self):
        self.running = False

pipeline = DataPipeline()

@app.on_event("startup")
async def startup():
    await pipeline.start()
    redis_client.set("pipeline:status", "running")

@app.on_event("shutdown")
async def shutdown():
    pipeline.stop()

@app.get("/")
async def root():
    return {"service": "Data Pipeline", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "pipeline_running": pipeline.running}

@app.get("/api/v1/stats")
async def get_stats():
    return {"stats": pipeline.stats, "timestamp": datetime.utcnow().isoformat()}

@app.get("/api/v1/observations/recent")
async def get_recent_observations(limit: int = 100):
    session = Session()
    try:
        observations = session.query(CrowdObservation).order_by(
            CrowdObservation.timestamp.desc()
        ).limit(limit).all()
        return {
            "observations": [
                {"zone_id": o.zone_id, "density": o.density, "timestamp": o.timestamp.isoformat()}
                for o in observations
            ],
            "count": len(observations)
        }
    finally:
        session.close()

@app.get("/api/v1/locations/recent")
async def get_recent_locations(limit: int = 100):
    session = Session()
    try:
        locations = session.query(UserLocation).order_by(
            UserLocation.timestamp.desc()
        ).limit(limit).all()
        return {
            "locations": [
                {"user_id": l.user_id, "zone_id": l.zone_id, "x": l.x, "y": l.y, "timestamp": l.timestamp.isoformat()}
                for l in locations
            ],
            "count": len(locations)
        }
    finally:
        session.close()

@app.get("/api/v1/orders/recent")
async def get_recent_orders(limit: int = 100):
    session = Session()
    try:
        orders = session.query(FoodOrder).order_by(
            FoodOrder.created_at.desc()
        ).limit(limit).all()
        return {
            "orders": [
                {"order_id": o.order_id, "user_id": o.user_id, "vendor_id": o.vendor_id, "status": o.status}
                for o in orders
            ],
            "count": len(orders)
        }
    finally:
        session.close()

@app.get("/api/v1/alerts/recent")
async def get_recent_alerts(limit: int = 100):
    session = Session()
    try:
        alerts = session.query(EmergencyAlert).order_by(
            EmergencyAlert.created_at.desc()
        ).limit(limit).all()
        return {
            "alerts": [
                {"alert_id": a.alert_id, "zone_id": a.zone_id, "alert_type": a.alert_type, "severity": a.severity}
                for a in alerts
            ],
            "count": len(alerts)
        }
    finally:
        session.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)