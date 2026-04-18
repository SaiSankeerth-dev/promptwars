FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn redis kafka-python numpy pandas scikit-learn torch

COPY . .

EXPOSE 8001

CMD ["python", "main.py"]