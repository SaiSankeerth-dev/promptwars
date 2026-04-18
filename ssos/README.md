# Smart Stadium Operating System (SSOS)

Production-grade AI platform for 100K+ venue intelligence.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                      USER LAYER                             │
│  Mobile App · Kiosks · Wearables · Web Dashboard           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                     SENSING LAYER                           │
│  Cameras · IoT Sensors · BLE Beacons · Wi-Fi RTT           │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      EDGE LAYER                              │
│  Real-time Inference · Anonymization · Local Decisions     │
└─────────────────────────────────────────────────────────────┘
                              │
┌─────────────────────────────────────────────────────────────┐
│                      CLOUD LAYER                            │
│  ML Training · Analytics · Digital Twin · Decision Engine  │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Start core services
docker-compose up -d

# Run mobile app
cd mobile-app && npm start

# Start edge node simulation
cd edge-node && python main.py
```

## Core Services

| Service | Port | Description |
|---------|------|-------------|
| API Gateway | 8000 | Authentication, routing |
| Crowd Prediction | 8001 | ML inference engine |
| Routing Engine | 8002 | Path optimization |
| Decision Engine | 8003 | Real-time decisions |
| Data Pipeline | 8004 | Kafka consumer |
| Digital Twin | 8005 | Simulation engine |

## Documentation

- [System Design](docs/SYSTEM_DESIGN.md)
- [API Reference](docs/API.md)
- [Deployment Guide](docs/DEPLOYMENT.md)
- [AI Models](docs/ML_MODELS.md)

## License

MIT License - Built for the stadium of the future.