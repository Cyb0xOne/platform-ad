FROM python:3.11-slim

WORKDIR /app

# openssh-client dipakai endpoint authorized_key untuk menitipkan pubkey ke vulnbox.
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .
COPY static ./static

# FORCAD_DSN diberikan lewat environment (lihat docker-compose.yml).
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
