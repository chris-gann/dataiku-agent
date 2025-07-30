"""
Health check endpoints for Dataiku Agent.

This module provides health check functionality for monitoring
the application's health and readiness.
"""
import json
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, Any, Optional

from ..core.config import Config
from ..core.logging import get_logger

logger = get_logger(__name__)


class HealthCheckHandler(BaseHTTPRequestHandler):
    """HTTP handler for health check endpoints."""
    
    def __init__(self, *args, assistant=None, metrics_collector=None, **kwargs):
        self.assistant = assistant
        self.metrics_collector = metrics_collector
        super().__init__(*args, **kwargs)
    
    def do_GET(self):
        """Handle GET requests."""
        if self.path == "/health":
            self._handle_health()
        elif self.path == "/health/live":
            self._handle_liveness()
        elif self.path == "/health/ready":
            self._handle_readiness()
        elif self.path == "/metrics":
            self._handle_metrics()
        else:
            self.send_error(404, "Not Found")
    
    def _handle_health(self):
        """Handle comprehensive health check."""
        health_status = self._get_health_status()
        
        # Determine overall status
        is_healthy = all(
            check["status"] == "healthy"
            for check in health_status["checks"].values()
        )
        
        status_code = 200 if is_healthy else 503
        
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        
        response = json.dumps(health_status, indent=2)
        self.wfile.write(response.encode())
    
    def _handle_liveness(self):
        """Handle liveness probe (is the app running?)."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        
        response = json.dumps({
            "status": "alive",
            "timestamp": datetime.utcnow().isoformat() + "Z"
        })
        self.wfile.write(response.encode())
    
    def _handle_readiness(self):
        """Handle readiness probe (is the app ready to serve requests?)."""
        # Check if all services are connected
        if self.assistant:
            connections = self.assistant.test_connections()
            is_ready = all(connections.values())
        else:
            is_ready = False
        
        status_code = 200 if is_ready else 503
        
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        
        response = json.dumps({
            "status": "ready" if is_ready else "not_ready",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "services": connections if self.assistant else {}
        })
        self.wfile.write(response.encode())
    
    def _handle_metrics(self):
        """Handle metrics endpoint."""
        if not self.metrics_collector:
            self.send_error(503, "Metrics not available")
            return
        
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        
        metrics = self.metrics_collector.export_prometheus()
        self.wfile.write(metrics.encode())
    
    def _get_health_status(self) -> Dict[str, Any]:
        """Get comprehensive health status."""
        status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "checks": {}
        }
        
        # Check service connections
        if self.assistant:
            connections = self.assistant.test_connections()
            
            # Brave Search health
            status["checks"]["brave_search"] = {
                "status": "healthy" if connections.get("brave_search") else "unhealthy",
                "message": "Connected" if connections.get("brave_search") else "Connection failed"
            }
            
            # OpenAI health
            status["checks"]["openai"] = {
                "status": "healthy" if connections.get("openai") else "unhealthy",
                "message": "Connected" if connections.get("openai") else "Connection failed"
            }
            
            # Cache health
            status["checks"]["cache"] = {
                "status": "healthy" if connections.get("cache") else "unhealthy",
                "message": "Connected" if connections.get("cache") else "Connection failed"
            }
            
            # Get additional metrics
            metrics = self.assistant.get_metrics()
            
            # Add token usage info
            if "openai_token_usage" in metrics:
                token_usage = metrics["openai_token_usage"]
                status["checks"]["openai"]["token_usage"] = {
                    "total": token_usage.get("total_tokens", 0),
                    "estimated_cost_usd": token_usage.get("estimated_cost_usd", 0)
                }
            
            # Add cache stats
            if "cache_stats" in metrics:
                cache_stats = metrics["cache_stats"]
                status["checks"]["cache"]["stats"] = cache_stats
        
        return status
    
    def log_message(self, format, *args):
        """Override to reduce logging noise."""
        # Only log errors
        if args[1] != '200':
            logger.info("health_check_request", method=args[0], path=args[1], status=args[2])


def start_health_server(
    config: Config,
    assistant: Any,
    metrics_collector: Any
) -> threading.Thread:
    """
    Start the health check server in a separate thread.
    
    Args:
        config: Application configuration
        assistant: DataikuAssistant instance
        metrics_collector: MetricsCollector instance
        
    Returns:
        Thread running the health server
    """
    def run_server():
        # Create custom handler class with dependencies
        handler = lambda *args, **kwargs: HealthCheckHandler(
            *args,
            assistant=assistant,
            metrics_collector=metrics_collector,
            **kwargs
        )
        
        server = HTTPServer(
            ("0.0.0.0", config.monitoring.health_check_port),
            handler
        )
        
        logger.info(
            "health_server_started",
            port=config.monitoring.health_check_port,
            endpoints=["/health", "/health/live", "/health/ready", "/metrics"]
        )
        
        try:
            server.serve_forever()
        except Exception as e:
            logger.error("health_server_error", error=str(e))
        finally:
            server.server_close()
    
    thread = threading.Thread(target=run_server, daemon=True)
    thread.start()
    
    return thread 