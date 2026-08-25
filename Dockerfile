FROM mcr.microsoft.com/playwright:v1.40.0-jammy

# Set python environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DATA_DIR=/data

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Expose server port (default 8082, overridden by Render's PORT env)
EXPOSE 8082

# Start the Flask application
CMD ["python3", "app.py"]
