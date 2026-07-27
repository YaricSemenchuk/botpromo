FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
COPY config ./config

RUN pip install --no-cache-dir .

ENV DB_PATH=/data/tgparser.db
ENV GROUPS_PATH=/app/config/groups.yaml

VOLUME ["/data"]

CMD ["python", "-m", "tgparser.main"]
