FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn redis kafka-python pydantic

COPY . .

EXPOSE 8003

CMD ["python", "main.py"]