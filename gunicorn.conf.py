# Gunicorn configuration for production deployment on Cloud Run
import os
import multiprocessing

# Server socket
bind = f"0.0.0.0:{os.environ.get('PORT', '8080')}"
backlog = 2048

# Worker processes
workers = int(os.environ.get('WEB_CONCURRENCY', multiprocessing.cpu_count() * 2 + 1))
worker_class = "gthread"
threads = int(os.environ.get('THREADS', 4))
worker_connections = 1000
max_requests = 1000
max_requests_jitter = 50

# Restart workers after this many requests, with up to 50 random extra requests
# This helps prevent memory leaks
preload_app = True

# Timeout configuration
timeout = 30  # Short timeout for HTTP responses (we ACK quickly)
keepalive = 2

# Logging
loglevel = os.environ.get('LOG_LEVEL', 'info').lower()
accesslog = '-'
errorlog = '-'
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'dataiku-agent'

# Security
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# Performance
max_worker_connections = 1000

def when_ready(server):
    server.log.info("Dataiku Agent server ready at %s", bind)

def on_starting(server):
    server.log.info("Starting Dataiku Agent with %d workers, %d threads each", workers, threads)

def worker_abort(worker):
    worker.log.info("Worker received SIGABRT signal")