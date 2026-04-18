FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn redis kafka-python numpy pandas scikit-learn torch

COPY . .

ENV MODEL_PATH=/app/crowd_lstm.pt

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
