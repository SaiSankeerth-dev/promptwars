FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi uvicorn redis numpy

COPY . .

EXPOSE 8005

CMD ["python", "main.py"]