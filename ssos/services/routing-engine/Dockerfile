FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn redis heapq dataclasses

COPY . .

EXPOSE 8002

CMD ["python", "main.py"]