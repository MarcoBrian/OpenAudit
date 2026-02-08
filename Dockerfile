FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including DNS utilities
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy pip config for better PyPI connectivity
COPY pip.conf /etc/pip.conf

# Upgrade pip and install build dependencies
RUN pip install --upgrade pip setuptools wheel

# Copy requirements in batches for better reliability
COPY requirements-core.txt /app/requirements-core.txt
COPY requirements-langchain.txt /app/requirements-langchain.txt
COPY requirements-other.txt /app/requirements-other.txt

# Install packages in batches with multiple retry strategies
RUN for i in 1 2 3; do \
        pip install --no-cache-dir --prefer-binary -r requirements-core.txt && break || \
        (echo "Attempt $i failed, retrying..." && sleep 10); \
    done

RUN for i in 1 2 3; do \
        pip install --no-cache-dir --prefer-binary -r requirements-langchain.txt && break || \
        (echo "Attempt $i failed, retrying..." && sleep 10); \
    done

RUN for i in 1 2 3; do \
        pip install --no-cache-dir --prefer-binary -r requirements-other.txt && break || \
        (echo "Attempt $i failed, retrying..." && sleep 10); \
    done

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
