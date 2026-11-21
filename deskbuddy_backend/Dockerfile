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

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install package in editable mode
COPY pyproject.toml .
RUN pip install --no-cache-dir -e .

# Copy source code
COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini .

# Create necessary directories
RUN mkdir -p /app/data /app/models /app/logs /app/credentials

# Expose port
EXPOSE 8080

# Run the application
CMD ["python", "-m", "app.main"]