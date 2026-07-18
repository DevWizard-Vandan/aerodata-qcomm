# Base image targeting stable, lightweight Debian python runtimes
FROM python:3.10-slim

# Set environment paths to optimize python logging & execution
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8501

# Set the operational workspace
WORKDIR /app

# Install system dependencies required for compiling network libraries & DB interfaces
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy python dependencies layout
COPY requirements.txt .

# Execute python dependency compilation
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copy all application directories & files into the image
COPY . .

# Expose Streamlit default network traffic port
EXPOSE 8501
