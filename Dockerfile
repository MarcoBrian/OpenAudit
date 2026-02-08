FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project (from project root)
COPY . /app/

# Set Python path
ENV PYTHONPATH=/app

# Create necessary directories
RUN mkdir -p /app/dashboard/runs /app/dashboard/runs/agent_sessions

# Expose the port FastAPI will run on
EXPOSE 8000

# Run the FastAPI server
CMD ["uvicorn", "dashboard.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
