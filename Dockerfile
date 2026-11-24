# One container that serves both the API and the built web page (Cloud Run).
# Built by Google Cloud Build: gcloud run deploy --source . (see README).

# --- Stage 1: build the web page (Node is only needed here, not at runtime) ---
FROM node:24-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- Stage 2: the API ---
FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never PYTHONUNBUFFERED=1
WORKDIR /app/backend

# Dependencies first, so this layer is reused when only our code changes.
COPY backend/pyproject.toml backend/uv.lock backend/.python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/app ./app
COPY backend/scripts ./scripts
# Popularity data: download the Tranco list at build time (refreshed on every deploy).
RUN .venv/bin/python -m scripts.fetch_tranco

# FastAPI serves the page from /app/web/dist (see app/main.py).
COPY --from=web /web/dist /app/web/dist

# Cloud Run's front end appends exactly one X-Forwarded-For entry (see app/ratelimit.py).
ENV PORT=8080 TRUSTED_PROXY_HOPS=1
RUN useradd --create-home appuser && chown -R appuser /app
USER appuser
CMD ["sh", "-c", "exec .venv/bin/fastapi run app/main.py --host 0.0.0.0 --port ${PORT}"]
