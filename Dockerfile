# Use Python 3.11 slim image for smaller size and better performance
FROM python:3.11-slim

# Set environment variables for production
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WEB_CONCURRENCY=2 \
    THREADS=4

# Create a non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser

# Set working directory
WORKDIR /app

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies with optimizations
RUN pip install --no-cache-dir --compile -r requirements.txt && \
    python -m compileall -b /usr/local/lib/python3.11/site-packages/ && \
    find /usr/local/lib/python3.11/site-packages/ -name '*.py' -delete && \
    find /usr/local/lib/python3.11/site-packages/ -name '__pycache__' -type d -exec rm -rf {} + || true

# Copy application code and configuration
COPY src/ ./src/
COPY manifest.json .
COPY gunicorn.conf.py .

# Pre-compile Python bytecode for faster startup
RUN python -m compileall -b src/ && \
    find src/ -name '*.py' -delete || true

# Change ownership to non-root user
RUN chown -R appuser:appuser /app
USER appuser

# Expose port (Cloud Run will inject the PORT environment variable)
EXPOSE 8080

# Health check endpoint (optional but recommended)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8080/health', timeout=10)" || exit 1

# Command to run the application with Gunicorn
CMD ["gunicorn", "--config", "gunicorn.conf.py", "src.app:application"]