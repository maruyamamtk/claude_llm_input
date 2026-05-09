# Stage 1: Dependency builder
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./

# Install runtime dependencies into .venv (no project code, no dev deps)
RUN uv sync --frozen --no-dev --no-install-project

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /app/.venv /app/.venv

# Copy source code
COPY . .

ENV PATH="/app/.venv/bin:$PATH"

# Install Chromium browser and its system dependencies (Playwright)
RUN playwright install chromium --with-deps

ENTRYPOINT ["python", "main.py"]
