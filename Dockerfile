FROM python:3.11-slim

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY src/ /app/src/

ENV PYTHONPATH=/app/src \
    LS_SPEC_ROOT=/workspace/ls-spec

CMD ["python", "-m", "ls_azure_night_runner"]
