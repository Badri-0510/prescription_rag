# Use Python 3.11 base image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy dependencies and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all app files
COPY . .

# Set PORT variable for Cloud Run
ENV PORT=8080

# Start your app
CMD ["python", "app.py"]
