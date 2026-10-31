# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.14-trixie-slim

ARG APP_VERSION
ARG UID=1000
ARG GID=1000
ARG APP_USER=app

LABEL org.opencontainers.image.version=$APP_VERSION

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_NO_DEV=1 \
    UV_LINK_MODE=copy

# Create a non-root user whose UID/GID can be matched to the host user
RUN groupadd --gid "${GID}" "${APP_USER}" \
    && useradd --uid "${UID}" --gid "${GID}" --create-home --shell /bin/bash "${APP_USER}" \
    && mkdir -p /app \
    && chown -R "${APP_USER}:${APP_USER}" /app

WORKDIR /app

# Copy dependency metadata first for better layer caching
COPY --chown=${APP_USER}:${APP_USER} .python-version pyproject.toml uv.lock /app/

# Install Python and project dependencies as the non-root user
USER ${APP_USER}
ENV PATH="/app/.venv/bin:${PATH}"

RUN uv sync --frozen --no-dev --no-install-project

# Copy application source
COPY --chown=${APP_USER}:${APP_USER} src /app/src
COPY --chown=${APP_USER}:${APP_USER} README.md /app/README.md
COPY --chown=${APP_USER}:${APP_USER} entrypoint.sh /app/entrypoint.sh
RUN mkdir -p /app/logs

RUN chmod +x /app/entrypoint.sh

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["run"]

