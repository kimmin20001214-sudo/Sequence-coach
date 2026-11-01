FROM node:22-slim AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/ backend/
COPY --from=frontend /frontend/dist frontend/dist
WORKDIR /app/backend
ENV FRONTEND_DIST=/app/frontend/dist
CMD ["sh", "-c", "uvicorn app.server:server --host 0.0.0.0 --port ${PORT:-8000}"]
