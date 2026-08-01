FROM node:24-bookworm AS frontend-build

WORKDIR /build

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


FROM python:3.11-slim

WORKDIR /app

# openssh-client dipakai endpoint authorized_key untuk menitipkan pubkey ke vulnbox.
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client \
 && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app.py .
COPY backend/admin_app.py .
COPY backend/static ./static
COPY --from=frontend-build /build/dist/next/index.html ./react/index.html
COPY --from=frontend-build /build/dist/admin/index.html ./react/admin/index.html
COPY --from=frontend-build /build/dist/assets/ ./react/assets/

# FORCAD_DSN diberikan lewat environment (lihat docker-compose.yml).
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
