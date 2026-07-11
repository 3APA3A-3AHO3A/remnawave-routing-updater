FROM python:3.12-alpine

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

HEALTHCHECK --interval=5m --timeout=10s --start-period=3m --retries=3 \
    CMD ["python", "-m", "routing_updater.healthcheck"]

CMD ["python", "-u", "-m", "routing_updater"]
