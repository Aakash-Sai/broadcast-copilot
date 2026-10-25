FROM node:24-bookworm-slim AS frontend
WORKDIR /build
RUN npm install --global pnpm@11.25.0
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend ./frontend
COPY tsconfig.json vite.config.ts ./
RUN pnpm build

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOST=0.0.0.0 PORT=8080 \
    EDITORIAL_DB_PATH=/var/lib/broadcast/editorial.sqlite3
WORKDIR /app
COPY requirements.lock.txt ./
RUN pip install --no-cache-dir -r requirements.lock.txt \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /var/lib/broadcast && chown app:app /var/lib/broadcast
COPY backend ./backend
COPY scripts/backup_editorial.py ./scripts/backup_editorial.py
COPY data ./data
COPY --from=frontend /build/dist ./dist
USER app
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health/ready', timeout=4)"
CMD ["python", "-m", "backend.serve"]
