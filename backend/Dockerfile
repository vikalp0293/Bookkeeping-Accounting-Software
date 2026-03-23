# --- Stage 1: Builder ---
# We use 'python:3.9-slim-bookworm' to ensure we are on a STABLE Linux version
FROM python:3.9-slim-bookworm AS builder
 
WORKDIR /app
 
# Install system dependencies
# libpq-dev is needed to COMPILE psycopg2 (database driver)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
&& rm -rf /var/lib/apt/lists/*
 
COPY requirements.txt .
 
# Install dependencies into /install folder
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt
 
 
# --- Stage 2: Runtime ---
FROM python:3.9-slim-bookworm
 
WORKDIR /app
 
# Install runtime libraries
# CORRECTION: The package is 'libpq5', not 'libpq-5'
# Also install poppler-utils for PDF to image conversion (required by pdf2image)
RUN apt-get update && apt-get install -y \
    libpq5 \
    poppler-utils \
&& rm -rf /var/lib/apt/lists/*
 
# Copy the installed python packages from the Builder stage
COPY --from=builder /install /usr/local
 
COPY . .
 
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
 
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
 
EXPOSE 8000
 
ENTRYPOINT ["/entrypoint.sh"]