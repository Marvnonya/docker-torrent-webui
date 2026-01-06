# Base image
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y mktorrent mediainfo ffmpeg && \
    rm -rf /var/lib/apt/lists/*

# Installing Python dependencies (requests and openai added)
RUN pip install --no-cache-dir flask requests openai

# Copy the code for the current directory
COPY . .

# Exposed port
EXPOSE 5000

# Start command
CMD ["python", "app.py"]
