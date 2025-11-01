# Use Python 3.11 base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all app files
COPY . .

# Create necessary directories
RUN mkdir -p uploads templates

# Set PORT variable for Cloud Run
ENV PORT=8080

# Use gunicorn for production
CMD exec gunicorn --bind :$PORT --workers 1 --threads 4 --timeout 600 --worker-class gthread --worker-tmp-dir /dev/shm app:app
```

**Key configurations for your ML dependencies:**
- Added build tools for torch and sentence-transformers
- Increased timeout to 600s (10 min) for model loading and processing
- Using `/dev/shm` for worker temp directory (better for Cloud Run)
- Reduced threads to 4 (your app is ML-heavy)

## 2. Create `.dockerignore`
```
