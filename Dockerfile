FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY config ./config

RUN pip install --no-cache-dir .

ENV DB_PATH=/data/tgparser.db
ENV GROUPS_PATH=/app/config/groups.yaml

# Persistent storage for /data (SQLite outbox/checkpoints) is attached as a
# Railway Volume via the dashboard/railway.json — Railway's builder rejects
# the Docker VOLUME instruction, so it must not be declared here.

CMD ["python", "-m", "tgparser.main"]
