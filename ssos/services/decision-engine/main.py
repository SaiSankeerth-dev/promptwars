import os
import json
import time
import asyncio
import random
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum
from fastapi import FastAPI
import redis

app = FastAPI(title="Real-Time Decision Engine", version="1.0.0")

redis_client = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=6379,
    decode_responses=True
)

KAFKA_BROKERS = os.getenv("KAFKA_BROKERS", "localhost:29092").split(",")

class AlertSeverity(Enum):
    INFO = 1
    WARNING = 2
    CRITICAL = 3
    EMERGENCY = 4

class ActionType(Enum):
    REROUTE_USERS = "reroute_users"
    OPEN_GATE = "open_gate"
    CLOSE_GATE = "close_gate"
    ALERT_STAFF = "alert_staff"
    BROADCAST_MESSAGE = "broadcast_message"
    TRIGGER_EVACUATION = "trigger_evacuation"
    ADJUST_PRICING = "adjust_pricing"
    NONE = "none"

@dataclass
class DecisionRule:
    name: str
    condition: str
    threshold: float
    action: ActionType
    priority: int
    cooldown_seconds: int

class RuleEngine:
    def __init__(self):
        self.rules = self._initialize_rules()
        self.action_history = []
        
    def _initialize_rules(self) -> List[DecisionRule]:
        return [
            DecisionRule(
                name="High Density Gate",
                condition="density",
                threshold=85,
                action=ActionType.REROUTE_USERS,
                priority=1,
                cooldown_seconds=300
            ),
            DecisionRule(
                name="Critical Density",
                condition="density",
                threshold=95,
                action=ActionType.ALERT_STAFF,
                priority=1,
                cooldown_seconds=60
            ),
            DecisionRule(
                name="Long Queue",
                condition="queue_time",
                threshold=15,
                action=ActionType.OPEN_GATE,
                priority=2,
                cooldown_seconds=180
            ),
            DecisionRule(
                name="Stampede Risk",
                condition="stampede_score",
                threshold=70,
                action=ActionType.TRIGGER_EVACUATION,
                priority=1,
                cooldown_seconds=0
            ),
            DecisionRule(
                name="Food Court Congestion",
                condition="density",
                threshold=80,
                action=ActionType.BROADCAST_MESSAGE,
                priority=3,
                cooldown_seconds=600
            ),
            DecisionRule(
                name="Restroom Congestion",
                condition="density",
                threshold=75,
                action=ActionType.BROADCAST_MESSAGE,
                priority=2,
                cooldown_seconds=300
            ),
        ]
    
    def evaluate(self, zone_id: str, metrics: Dict) -> Optional[Dict]:
        triggered_rules = []
        
        for rule in self.rules:
            if rule.name in self.action_history:
                continue
                
            value = metrics.get(rule.condition)
            if value is None:
                continue
                
            if value >= rule.threshold:
                triggered_rules.append({
                    "rule": rule.name,
                    "value": value,
                    "threshold": rule.threshold,
                    "action": rule.action.value,
                    "priority": rule.priority
                })
                
                self.action_history.append(rule.name)
                
                if rule.cooldown_seconds > 0:
                    asyncio.create_task(self._reset_rule(rule.name, rule.cooldown_seconds))
        
        if triggered_rules:
            return {
                "zone_id": zone_id,
                "triggered_rules": triggered_rules,
                "primary_action": triggered_rules[0]["action"],
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return None
    
    async def _reset_rule(self, rule_name: str, cooldown: int):
        await asyncio.sleep(cooldown)
        if rule_name in self.action_history:
            self.action_history.remove(rule_name)

class AnomalyDetector:
    def __init__(self):
        self.baseline_metrics = {
            "velocity_change_threshold": 3.0,
            "density_spike_threshold": 30,
            "retrograde_flow_threshold": 0.2,
            "temperature_threshold": 35
        }
        
    def detect(self, zone_id: str, observations: Dict) -> Optional[Dict]:
        anomalies = []
        
        velocity = observations.get("avg_velocity", 0)
        prev_velocity = observations.get("prev_velocity", 0)
        velocity_change = abs(velocity - prev_velocity) / max(prev_velocity, 0.1)
        
        if velocity_change > self.baseline_metrics["velocity_change_threshold"]:
            anomalies.append({
                "type": "velocity_spike",
                "severity": "high",
                "value": velocity_change,
                "threshold": self.baseline_metrics["velocity_change_threshold"]
            })
        
        density = observations.get("density", 0)
        prev_density = observations.get("prev_density", 0)
        density_change = density - prev_density
        
        if density_change > self.baseline_metrics["density_spike_threshold"]:
            anomalies.append({
                "type": "density_spike",
                "severity": "critical" if density > 85 else "high",
                "value": density_change,
                "threshold": self.baseline_metrics["density_spike_threshold"]
            })
        
        retrograde_ratio = observations.get("retrograde_ratio", 0)
        if retrograde_ratio > self.baseline_metrics["retrograde_flow_threshold"]:
            anomalies.append({
                "type": "retrograde_flow",
                "severity": "critical",
                "value": retrograde_ratio,
                "threshold": self.baseline_metrics["retrograde_flow_threshold"]
            })
        
        if anomalies:
            return {
                "zone_id": zone_id,
                "anomalies": anomalies,
                "risk_score": self._calculate_risk_score(anomalies),
                "timestamp": datetime.utcnow().isoformat()
            }
        
        return None
    
    def _calculate_risk_score(self, anomalies: List[Dict]) -> int:
        severity_weights = {"low": 10, "medium": 30, "high": 60, "critical": 100}
        total = sum(severity_weights.get(a.get("severity", "low"), 10) for a in anomalies)
        return min(100, total)

class ActionExecutor:
    def __init__(self):
        self.execution_history = []
        
    async def execute(self, decision: Dict) -> Dict:
        action = decision.get("primary_action", ActionType.NONE.value)
        zone_id = decision.get("zone_id")
        
        result = {
            "action": action,
            "zone_id": zone_id,
            "status": "pending",
            "timestamp": datetime.utcnow().isoformat()
        }
        
        if action == ActionType.REROUTE_USERS.value:
            result["details"] = f"Routing users away from {zone_id} to less congested areas"
            result["affected_users"] = random.randint(50, 500)
            
        elif action == ActionType.OPEN_GATE.value:
            result["details"] = f"Opening additional gates near {zone_id}"
            result["gates_affected"] = ["gate_b", "gate_c"]
            
        elif action == ActionType.ALERT_STAFF.value:
            result["details"] = f"Alerting staff to {zone_id}"
            result["staff_notified"] = random.randint(5, 20)
            
        elif action == ActionType.BROADCAST_MESSAGE.value:
            result["details"] = f"Broadcasting message about congestion at {zone_id}"
            result["channels"] = ["app", "signage", "audio"]
            
        elif action == ActionType.TRIGGER_EVACUATION.value:
            result["details"] = f"Initiating evacuation protocol for {zone_id}"
            result["protocol"] = "EVACUATION_ZONE_A"
            result["severity"] = "critical"
            
        elif action == ActionType.NONE.value:
            result["details"] = "No action required"
        
        result["status"] = "executed"
        self.execution_history.append(result)
        
        redis_client.publish("decision_actions", json.dumps(result))
        
        return result

class DecisionEngine:
    def __init__(self):
        self.rule_engine = RuleEngine()
        self.anomaly_detector = AnomalyDetector()
        self.action_executor = ActionExecutor()
        self.decision_history = []
        
    async def process_zone(self, zone_id: str, metrics: Dict) -> Dict:
        decision = self.rule_engine.evaluate(zone_id, metrics)
        
        if not decision:
            observations = {
                "density": metrics.get("density", 0),
                "prev_density": metrics.get("prev_density", 0),
                "avg_velocity": metrics.get("avg_velocity", 0),
                "prev_velocity": metrics.get("prev_velocity", 0),
                "retrograde_ratio": metrics.get("retrograde_ratio", 0)
            }
            anomaly_result = self.anomaly_detector.detect(zone_id, observations)
            
            if anomaly_result and anomaly_result["risk_score"] > 50:
                decision = {
                    "zone_id": zone_id,
                    "triggered_rules": [{"rule": "Anomaly Detection", "action": anomaly_result["anomalies"][0]["type"]}],
                    "primary_action": ActionType.ALERT_STAFF.value,
                    "anomaly": anomaly_result,
                    "timestamp": datetime.utcnow().isoformat()
                }
        
        if decision:
            execution_result = await self.action_executor.execute(decision)
            decision["execution"] = execution_result
            self.decision_history.append(decision)
            
            redis_client.set(f"decision:latest:{zone_id}", json.dumps(decision))
            
        return decision
    
    def get_decision_summary(self) -> Dict:
        recent = self.decision_history[-20:] if len(self.decision_history) > 20 else self.decision_history
        
        action_counts = {}
        for d in recent:
            action = d.get("primary_action", "none")
            action_counts[action] = action_counts.get(action, 0) + 1
            
        return {
            "total_decisions": len(self.decision_history),
            "recent_decisions": len(recent),
            "action_breakdown": action_counts,
            "last_decision": self.decision_history[-1] if self.decision_history else None
        }

decision_engine = DecisionEngine()

@app.on_event("startup")
async def startup():
    redis_client.set("decision:engine:status", "running")
    redis_client.set("decision:engine:started_at", datetime.utcnow().isoformat())

@app.get("/")
async def root():
    return {"service": "Decision Engine", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "rules_active": len(decision_engine.rule_engine.rules)}

@app.post("/api/v1/decisions/evaluate/{zone_id}")
async def evaluate_zone(zone_id: str, metrics: Dict):
    result = await decision_engine.process_zone(zone_id, metrics)
    if result:
        return result
    return {"status": "no_decision", "zone_id": zone_id}

@app.get("/api/v1/decisions/recent")
async def get_recent_decisions(limit: int = 20):
    return {"decisions": decision_engine.decision_history[-limit:], "count": len(decision_engine.decision_history)}

@app.get("/api/v1/decisions/summary")
async def get_decision_summary():
    return decision_engine.get_decision_summary()

@app.get("/api/v1/rules")
async def get_rules():
    return {"rules": [
        {"name": r.name, "condition": r.condition, "threshold": r.threshold, "action": r.action.value, "priority": r.priority}
        for r in decision_engine.rule_engine.rules
    ]}

@app.post("/api/v1/rules/add")
async def add_rule(rule: DecisionRule):
    decision_engine.rule_engine.rules.append(rule)
    return {"status": "added", "rule": rule.name}

@app.get("/api/v1/anomalies/active")
async def get_active_anomalies():
    return {"anomaly_detector_status": "active", "baselines": decision_engine.anomaly_detector.baseline_metrics}

@app.get("/api/v1/execution/history")
async def get_execution_history(limit: int = 20):
    return {"history": decision_engine.action_executor.execution_history[-limit:]}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)