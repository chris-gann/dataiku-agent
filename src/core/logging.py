"""
Enhanced logging configuration for Dataiku Agent.

This module provides structured logging with support for different
environments, log rotation, and integration with monitoring services.
"""
import sys
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import json

import structlog
from pythonjsonlogger import jsonlogger

from .config import Config, LogLevel, Environment


# Custom processors
def add_app_context(logger, method_name, event_dict):
    """Add application context to all log messages."""
    from .config import get_current_config
    
    try:
        config = get_current_config()
        event_dict["app_name"] = config.app_name
        event_dict["app_version"] = config.app_version
        event_dict["environment"] = config.environment.value
    except Exception:
        # If config is not available, use defaults
        event_dict["app_name"] = "dataiku-agent"
        event_dict["environment"] = "unknown"
    
    return event_dict


def add_timestamp(logger, method_name, event_dict):
    """Add ISO format timestamp."""
    event_dict["timestamp"] = datetime.utcnow().isoformat() + "Z"
    return event_dict


def censor_sensitive_data(logger, method_name, event_dict):
    """Remove sensitive data from logs."""
    sensitive_keys = {
        "token", "key", "secret", "password", "api_key", 
        "auth", "authorization", "bot_token", "app_token"
    }
    
    def censor_dict(d: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively censor sensitive data in dictionary."""
        censored = {}
        for k, v in d.items():
            if any(sensitive in k.lower() for sensitive in sensitive_keys):
                censored[k] = "***REDACTED***"
            elif isinstance(v, dict):
                censored[k] = censor_dict(v)
            elif isinstance(v, list):
                censored[k] = [
                    censor_dict(item) if isinstance(item, dict) else item
                    for item in v
                ]
            else:
                censored[k] = v
        return censored
    
    return censor_dict(event_dict)


def setup_logging(config: Config) -> None:
    """
    Set up logging configuration based on environment.
    
    Args:
        config: Application configuration
    """
    # Create log directory if it doesn't exist
    config.log_dir.mkdir(parents=True, exist_ok=True)
    
    # Configure processors based on environment
    processors: List[Any] = [
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        add_timestamp,
        add_app_context,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    
    # Add sensitive data censoring in production
    if config.environment == Environment.PRODUCTION:
        processors.append(censor_sensitive_data)
    
    # Choose renderer based on environment
    if config.environment in (Environment.STAGING, Environment.PRODUCTION):
        # JSON output for production/staging
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Pretty console output for development
        processors.append(structlog.dev.ConsoleRenderer())
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure standard logging
    log_level = getattr(logging, config.log_level.value)
    
    # Remove all existing handlers
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    
    if config.environment in (Environment.STAGING, Environment.PRODUCTION):
        # JSON formatter for production
        formatter = jsonlogger.JsonFormatter(
            "%(timestamp)s %(name)s %(levelname)s %(message)s",
            timestamp=True,
        )
        console_handler.setFormatter(formatter)
    else:
        # Standard formatter for development
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        console_handler.setFormatter(formatter)
    
    root_logger.addHandler(console_handler)
    root_logger.setLevel(log_level)
    
    # File handler for production
    if config.environment in (Environment.STAGING, Environment.PRODUCTION):
        from logging.handlers import RotatingFileHandler
        
        log_file = config.log_dir / f"{config.app_name.lower().replace(' ', '-')}.log"
        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=100 * 1024 * 1024,  # 100MB
            backupCount=10,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)
    
    # Configure third-party loggers
    logging.getLogger("slack_bolt").setLevel(
        logging.INFO if config.debug else logging.WARNING
    )
    logging.getLogger("slack_sdk").setLevel(
        logging.INFO if config.debug else logging.WARNING
    )
    logging.getLogger("openai").setLevel(
        logging.INFO if config.debug else logging.WARNING
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    
    # Sentry integration
    if config.monitoring.sentry_dsn:
        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration
            
            sentry_logging = LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR
            )
            
            sentry_sdk.init(
                dsn=config.monitoring.sentry_dsn.get_secret_value(),
                environment=config.environment.value,
                integrations=[sentry_logging],
                traces_sample_rate=config.monitoring.sentry_traces_sample_rate,
                attach_stacktrace=True,
                send_default_pii=False,
            )
        except ImportError:
            logger = structlog.get_logger()
            logger.warning("Sentry SDK not installed, skipping Sentry integration")


def get_logger(name: Optional[str] = None) -> structlog.BoundLogger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name. If None, uses the calling module's name.
        
    Returns:
        A bound logger instance.
    """
    if name is None:
        import inspect
        frame = inspect.currentframe()
        if frame and frame.f_back:
            name = frame.f_back.f_globals.get("__name__", "dataiku_agent")
        else:
            name = "dataiku_agent"
    
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding temporary log context."""
    
    def __init__(self, logger: structlog.BoundLogger, **kwargs):
        self.logger = logger
        self.context = kwargs
        self.token = None
    
    def __enter__(self):
        self.token = structlog.threadlocal.bind_threadlocal(**self.context)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.token:
            structlog.threadlocal.unbind_threadlocal(self.token)
        return False


def log_performance(logger: structlog.BoundLogger, operation: str):
    """
    Decorator to log operation performance.
    
    Args:
        logger: Logger instance
        operation: Name of the operation being performed
    """
    import functools
    import time
    
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            logger.info(f"{operation}_started")
            
            try:
                result = func(*args, **kwargs)
                duration_ms = int((time.time() - start_time) * 1000)
                
                logger.info(
                    f"{operation}_completed",
                    duration_ms=duration_ms,
                )
                
                return result
                
            except Exception as e:
                duration_ms = int((time.time() - start_time) * 1000)
                
                logger.error(
                    f"{operation}_failed",
                    duration_ms=duration_ms,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                raise
        
        return wrapper
    
    return decorator 