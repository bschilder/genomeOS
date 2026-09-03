FROM node:24-alpine AS map-ui

WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app
COPY pyproject.toml README.md ./
COPY genomeos ./genomeos
COPY --from=map-ui /web/out ./genomeos/static/map
COPY demo/artifacts ./demo/artifacts
COPY reference/ne_110m_countries.geojson ./reference/ne_110m_countries.geojson
RUN pip install --no-cache-dir '.[postgres,tabix,read]'

USER 65532:65532
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/ready', timeout=2)"
CMD ["sh", "-c", "uvicorn genomeos.api:app --host 0.0.0.0 --port ${PORT}"]
