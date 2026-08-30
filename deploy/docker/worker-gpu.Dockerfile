FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36 AS python-build
WORKDIR /app
RUN python -m pip install --no-cache-dir uv==0.11.18
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src/ src/
COPY experiments/ experiments/
RUN uv sync --frozen --no-dev --extra ml --no-editable && rm /app/.venv/.gitignore

FROM python:3.12-slim@sha256:229a2c5bfa27522db7815ea81f9bed70af17ccb9de9fc7ad142b1877b5830d36
ARG SOURCE_REVISION=unknown
ARG APP_VERSION=0.1.1
LABEL org.opencontainers.image.source="https://github.com/kuotunyu/mvtec-ad2-inspection-platform" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${APP_VERSION}" \
      org.opencontainers.image.revision="${SOURCE_REVISION:-unknown}"
RUN groupadd --gid 10001 inspection \
    && useradd --uid 10001 --gid inspection --no-create-home inspection \
    && mkdir -p /runtime/db /runtime/artifacts \
    && chown -R 10001:10001 /runtime
WORKDIR /app
COPY --from=python-build /app/.venv /app/.venv
COPY deploy/docker/entrypoint-worker.sh /usr/local/bin/entrypoint-worker
RUN chmod 0555 /usr/local/bin/entrypoint-worker
ENV PATH="/app/.venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
VOLUME ["/runtime/db", "/runtime/artifacts"]
HEALTHCHECK --interval=10s --timeout=3s --start-period=45s --retries=12 \
  CMD test -f /tmp/inspection-worker.ready
ENTRYPOINT ["entrypoint-worker"]
