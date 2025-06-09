FROM python:3.13-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get upgrade -y && apt-get install -y \
    ffmpeg \
    curl \
    build-essential \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Back to app directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app/ ./app/
COPY run.py .

# Create directory for generated videos
RUN mkdir -p /app/generated_videos

# Expose port
EXPOSE 3002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3002/health || exit 1

# Run with gunicorn for production
CMD ["gunicorn", "--bind", "0.0.0.0:3002", "--workers", "2", "--timeout", "600", "--worker-class", "sync", "app.main:create_app()"]