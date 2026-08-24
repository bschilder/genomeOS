FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY pyproject.toml README.md ./
COPY genomeos ./genomeos
RUN pip install --no-cache-dir '.[postgres,tabix]'

USER 65532:65532
CMD ["sh", "-c", "uvicorn genomeos.api:app --host 0.0.0.0 --port ${PORT}"]
