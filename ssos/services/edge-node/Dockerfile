FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn kafka-python opencv-python numpy redis

COPY . .

EXPOSE 8006

CMD ["python", "main.py"]