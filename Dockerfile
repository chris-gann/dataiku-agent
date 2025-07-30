# Multi-stage Dockerfile for Dataiku Agent

# Build stage
FROM python:3.11-slim as builder

# Install build dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

# Production stage
FROM python:3.11-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN useradd -m -u 1000 -s /bin/bash dataiku-agent

# Set working directory
WORKDIR /app

# Copy Python dependencies from builder
COPY --from=builder /root/.local /home/dataiku-agent/.local

# Copy application code
COPY --chown=dataiku-agent:dataiku-agent . .

# Create necessary directories
RUN mkdir -p /app/data /app/logs && \
    chown -R dataiku-agent:dataiku-agent /app/data /app/logs

# Switch to non-root user
USER dataiku-agent

# Update PATH
ENV PATH=/home/dataiku-agent/.local/bin:$PATH

# Set Python to unbuffered mode
ENV PYTHONUNBUFFERED=1

# Expose ports for health check and metrics
EXPOSE 8080 9090

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health/live')"

# Run the application
CMD ["python", "-m", "src.main"] 