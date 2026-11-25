# DeskBuddy Backend Dockerfile
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    libsndfile1 \
    libportaudio2 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies from pyproject.toml
COPY pyproject.toml .
COPY app/ ./app/
COPY web/ ./web/
COPY alembic/ ./alembic/
COPY alembic.ini .
COPY plugins.json .
RUN pip install --no-cache-dir -e .

# Create necessary directories
RUN mkdir -p /app/data /app/models /app/logs /app/credentials

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "-m", "app.main"]