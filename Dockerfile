FROM node:24-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package*.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libxrender1 libxext6 libsm6 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend/ ./backend/
RUN pip install --no-cache-dir '.[cad]'
COPY --from=frontend /build/frontend/dist/ ./frontend/dist/
RUN useradd --create-home --uid 10001 refit && mkdir -p /data && chown refit:refit /data
USER refit
ENV REFIT_DATA_DIR=/data REFIT_AI_PROVIDER=manual
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=3)"
CMD ["python","-m","uvicorn","backend.main:app","--host","0.0.0.0","--port","8000"]
