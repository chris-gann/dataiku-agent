"""
Main entry point for Dataiku Agent.

This module starts the application with proper configuration,
monitoring, and health checks.
"""
import signal
import sys
import threading
from pathlib import Path
from typing import Optional

from slack_bolt.adapter.socket_mode import SocketModeHandler

from .core import (
    Config,
    get_config,
    setup_logging,
    get_logger,
    Environment,
)
from .api import DataikuAssistant
from .monitoring import start_health_server, MetricsCollector


logger = get_logger(__name__)


class DataikuAgentApp:
    """Main application class."""
    
    def __init__(self, config_path: Optional[Path] = None):
        # Load configuration
        self.config = get_config(config_path)
        
        # Set up logging
        setup_logging(self.config)
        
        # Initialize components
        self.assistant = DataikuAssistant(self.config)
        self.socket_handler: Optional[SocketModeHandler] = None
        self.health_server_thread: Optional[threading.Thread] = None
        self.metrics_collector = MetricsCollector(self.config)
        
        # Set up signal handlers
        self._setup_signal_handlers()
        
        logger.info(
            "dataiku_agent_initialized",
            app_name=self.config.app_name,
            version=self.config.app_version,
            environment=self.config.environment.value,
        )
    
    def _setup_signal_handlers(self):
        """Set up graceful shutdown handlers."""
        def handle_shutdown(signum, frame):
            logger.info("shutdown_signal_received", signal=signum)
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, handle_shutdown)
        signal.signal(signal.SIGTERM, handle_shutdown)
    
    def start(self):
        """Start the application."""
        try:
            # Test connections
            logger.info("testing_service_connections")
            connection_results = self.assistant.test_connections()
            
            for service, status in connection_results.items():
                if not status:
                    logger.error(f"{service}_connection_failed")
                    if self.config.environment == Environment.PRODUCTION:
                        raise RuntimeError(f"Failed to connect to {service}")
            
            # Start health check server if monitoring is enabled
            if self.config.monitoring.enabled:
                logger.info(
                    "starting_health_server",
                    port=self.config.monitoring.health_check_port,
                )
                self.health_server_thread = start_health_server(
                    self.config,
                    self.assistant,
                    self.metrics_collector,
                )
            
            # Start Socket Mode handler
            self.socket_handler = SocketModeHandler(
                self.assistant.app,
                self.config.slack.app_token.get_secret_value(),
                connect_timeout=self.config.slack.socket_mode_timeout,
            )
            
            logger.info(
                "dataiku_agent_starting",
                bot_token_present=bool(self.config.slack.bot_token),
                app_token_present=bool(self.config.slack.app_token),
            )
            
            # Start the app
            logger.info("dataiku_agent_ready")
            self.socket_handler.start()
            
        except Exception as e:
            logger.error(
                "dataiku_agent_start_failed",
                error=str(e),
                error_type=type(e).__name__,
            )
            self.stop()
            raise
    
    def stop(self):
        """Stop the application gracefully."""
        logger.info("dataiku_agent_stopping")
        
        try:
            # Stop Socket Mode handler
            if self.socket_handler:
                self.socket_handler.close()
            
            # Stop health server
            if self.health_server_thread and self.health_server_thread.is_alive():
                # Health server will stop on next request
                self.health_server_thread.join(timeout=5)
            
            # Clean up assistant resources
            self.assistant.cleanup()
            
            logger.info("dataiku_agent_stopped")
            
        except Exception as e:
            logger.error(
                "dataiku_agent_stop_failed",
                error=str(e),
                error_type=type(e).__name__,
            )


def main():
    """Main entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Dataiku Agent for Slack")
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to configuration file (JSON)",
    )
    parser.add_argument(
        "--test-connections",
        action="store_true",
        help="Test connections and exit",
    )
    
    args = parser.parse_args()
    
    try:
        app = DataikuAgentApp(args.config)
        
        if args.test_connections:
            # Just test connections and exit
            results = app.assistant.test_connections()
            
            print("\nConnection Test Results:")
            print("-" * 30)
            for service, status in results.items():
                status_str = "✅ OK" if status else "❌ FAILED"
                print(f"{service:<15}: {status_str}")
            
            sys.exit(0 if all(results.values()) else 1)
        
        # Start the app
        app.start()
        
    except KeyboardInterrupt:
        logger.info("keyboard_interrupt_received")
        sys.exit(0)
    except Exception as e:
        logger.error(
            "fatal_error",
            error=str(e),
            error_type=type(e).__name__,
        )
        sys.exit(1)


if __name__ == "__main__":
    main() 