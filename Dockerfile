# Stage 1: Build frontend
FROM node:20-alpine AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python runtime
FROM python:3.13-slim AS runtime
WORKDIR /app

# Install Python deps
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[web]"

# Copy bot code
COPY bot/ bot/
COPY config/ config/

# Copy built frontend
COPY --from=frontend /app/frontend/dist frontend/dist

# Data volume for SQLite persistence
VOLUME /app/data

EXPOSE 8000

CMD ["python", "-m", "bot.main"]
