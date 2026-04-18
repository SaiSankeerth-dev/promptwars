import asyncio
import importlib.util
import json
import os
import sys
import types
from datetime import datetime, UTC
from pathlib import Path


class FakeRedis:
    def __init__(self):
        self.kv = {}
        self.hashes = {}
        self.sets = {}
        self.lists = {}
        self.channels = []

    def ping(self):
        return True

    def get(self, key):
        return self.kv.get(key)

    def set(self, key, value):
        self.kv[key] = str(value) if not isinstance(value, str) else value

    def hset(self, key, *args, mapping=None):
        bucket = self.hashes.setdefault(key, {})
        if mapping is not None:
            bucket.update({k: str(v) for k, v in mapping.items()})
        elif len(args) == 2:
            bucket[str(args[0])] = str(args[1])

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def sadd(self, key, value):
        self.sets.setdefault(key, set()).add(value)

    def scard(self, key):
        return len(self.sets.get(key, set()))

    def keys(self, pattern):
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            all_keys = list(self.kv.keys()) + list(self.hashes.keys()) + list(self.lists.keys())
            return sorted(k for k in all_keys if k.startswith(prefix))
        return [pattern] if pattern in self.kv or pattern in self.hashes or pattern in self.lists else []

    def publish(self, channel, message):
        self.channels.append((channel, message))

    def lpush(self, key, value):
        self.lists.setdefault(key, []).insert(0, value)

    def ltrim(self, key, start, end):
        if key in self.lists:
            self.lists[key] = self.lists[key][start:end + 1]

    def llen(self, key):
        return len(self.lists.get(key, []))

    def lrange(self, key, start, end):
        if key not in self.lists:
            return []
        return self.lists[key][start:end + 1]


class FakeKafkaProducer:
    def __init__(self, *args, **kwargs):
        pass

    def send(self, *args, **kwargs):
        return None


class FakeKafkaConsumer:
    def __init__(self, *args, **kwargs):
        pass

    def __iter__(self):
        return iter(())


def install_fake_modules():
    fake_redis_module = types.ModuleType("redis")
    fake_redis_module.Redis = lambda *args, **kwargs: FakeRedis()
    fake_aioredis_module = types.ModuleType("redis.asyncio")

    class FakeAsyncRedis:
        def pubsub(self):
            class FakePubSub:
                async def subscribe(self, *args, **kwargs):
                    return None

                async def listen(self):
                    if False:
                        yield None
                    return

                async def close(self):
                    return None

            return FakePubSub()

        async def aclose(self):
            return None

    fake_aioredis_module.from_url = lambda *args, **kwargs: FakeAsyncRedis()
    fake_redis_module.asyncio = fake_aioredis_module

    fake_kafka_module = types.ModuleType("kafka")
    fake_kafka_module.KafkaProducer = FakeKafkaProducer
    fake_kafka_module.KafkaConsumer = FakeKafkaConsumer

    sys.modules["redis"] = fake_redis_module
    sys.modules["redis.asyncio"] = fake_aioredis_module
    sys.modules["kafka"] = fake_kafka_module


def load_module(module_name: str, file_path: Path):
    sys.path.insert(0, str(file_path.parent))
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


async def main():
    root = Path(__file__).resolve().parents[1]
    checkpoint = root / "services" / "crowd-prediction" / "crowd_lstm.pt"
    if not checkpoint.exists():
        raise SystemExit("Checkpoint missing: services/crowd-prediction/crowd_lstm.pt")

    os.environ["MODEL_PATH"] = str(checkpoint)
    install_fake_modules()

    crowd = load_module("crowd_main", root / "services" / "crowd-prediction" / "main.py")
    decision = load_module("decision_main", root / "services" / "decision-engine" / "main.py")
    gateway = load_module("gateway_main", root / "services" / "api-gateway" / "main.py")

    shared = FakeRedis()
    crowd.redis_client = shared
    decision.redis_client = shared
    gateway.redis_client = shared
    gateway._fetch_json = lambda url: {"status": "healthy"}

    for zone in crowd.ZONES:
        shared.hset("stadium:zones", zone, json.dumps({"name": zone, "capacity": crowd.ZONE_CAPACITY.get(zone, 2000)}))

    for zone in crowd.ZONES[:3]:
        crowd.feature_buffer.push(zone, 40.0, 1.4)
        crowd.zone_density_history[zone].append(40.0)
        shared.set(f"density:{zone}", 40.0)
        shared.set(f"velocity:{zone}", 1.4)

    result = await crowd.trigger_surge({"zone": "gate_a", "target_density": 93, "velocity": 0.25})
    shared.set("predictions:all", json.dumps([crowd._infer_zone("gate_a")]))
    shared.set("predictions:updated_at", datetime.now(UTC).isoformat())
    await decision.decision_engine.process_crushguard_alert(result["crushguard"])

    shared.set("decision:engine:status", "running")
    shared.set(
        "digital_twin:state",
        json.dumps({"timestamp": datetime.now(UTC).isoformat(), "zones": {}, "total_agents": 1000}),
    )

    health = await gateway.demo_health()

    assert result["status"] == "surge_injected"
    assert result["crushguard"]["alert_level"] in {"warning", "danger"}
    assert health["checks"]["redis"]["ok"] is True
    assert health["checks"]["crowd_prediction"]["ok"] is True
    assert health["checks"]["routing_engine"]["ok"] is True
    assert health["checks"]["decision_engine"]["recent_decisions"] >= 1
    assert health["checks"]["predictions"]["zones"] >= 1
    assert health["checks"]["digital_twin"]["ok"] is True

    print("DEMO_SMOKE_OK")
    print(json.dumps({
        "surge_level": result["crushguard"]["alert_level"],
        "surge_confidence": result["crushguard"]["confidence"],
        "health_status": health["status"],
        "recent_decisions": health["checks"]["decision_engine"]["recent_decisions"],
    }, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
