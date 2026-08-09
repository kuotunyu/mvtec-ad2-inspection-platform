FROM node:24-alpine@sha256:d32cdf619f63fe0471182d08996dd516c6275bb5fd31ae06e55a570bd9e1ad43 AS web
WORKDIR /web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci --ignore-scripts
COPY apps/web/ ./
RUN npm run build

FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS python-build
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.11.18
COPY pyproject.toml uv.lock ./
COPY src/ src/
COPY experiments/ experiments/
RUN uv sync --frozen --no-dev --no-editable && rm /app/.venv/.gitignore

FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/kuotunyu/mvtec-ad2-inspection-platform" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.revision="${SOURCE_REVISION:-unknown}"
RUN groupadd --gid 10001 inspection \
    && useradd --uid 10001 --gid inspection --no-create-home inspection \
    && mkdir -p /runtime/db /runtime/artifacts \
    && chown -R 10001:10001 /runtime
WORKDIR /app
COPY --from=python-build /app/.venv /app/.venv
COPY apps/api/ apps/api/
COPY reports/ reports/
COPY alembic.ini ./
COPY src/inspection_platform/db/migrations/ src/inspection_platform/db/migrations/
COPY --from=web /web/dist apps/web/dist/
COPY deploy/docker/entrypoint-api.sh /usr/local/bin/entrypoint-api
RUN chmod 0555 /usr/local/bin/entrypoint-api
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
VOLUME ["/runtime/db", "/runtime/artifacts"]
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health/ready', timeout=2)"
ENTRYPOINT ["entrypoint-api"]
