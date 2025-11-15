FROM python:3.11-slim

WORKDIR /app

COPY src/ /app/src/

ENV PYTHONPATH=/app/src \
    LS_SPEC_ROOT=/workspace/ls-spec

CMD ["python", "-m", "ls_azure_night_runner"]
