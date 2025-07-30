"""
Configuration management for Dataiku Agent.

This module handles all configuration loading, validation, and management
with support for different environments (dev, staging, prod).
"""
import os
import json
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel, validator, Field, SecretStr


class Environment(str, Enum):
    """Application environment types."""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


class LogLevel(str, Enum):
    """Log level configuration."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class ReasoningEffort(str, Enum):
    """OpenAI o4-mini reasoning effort levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SlackConfig(BaseModel):
    """Slack-specific configuration."""
    bot_token: SecretStr = Field(..., description="Slack bot token")
    app_token: SecretStr = Field(..., description="Slack app token for Socket Mode")
    
    # Rate limiting
    rate_limit_per_minute: int = Field(default=20, ge=1, le=100)
    rate_limit_burst: int = Field(default=5, ge=1, le=20)
    
    # Timeouts
    socket_mode_timeout: int = Field(default=30, ge=10, le=120)
    api_timeout: int = Field(default=10, ge=5, le=30)
    
    # Retry configuration
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_backoff_base: float = Field(default=2.0, ge=1.0, le=5.0)


class OpenAIConfig(BaseModel):
    """OpenAI API configuration."""
    api_key: SecretStr = Field(..., description="OpenAI API key")
    model: str = Field(default="o4-mini", description="Model to use")
    reasoning_effort: ReasoningEffort = Field(default=ReasoningEffort.MEDIUM)
    max_completion_tokens: int = Field(default=1500, ge=100, le=4000)
    temperature: float = Field(default=0.3, ge=0.0, le=1.0)
    
    # Rate limiting
    rate_limit_per_minute: int = Field(default=60, ge=1, le=200)
    
    # Retry configuration
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_backoff_base: float = Field(default=2.0, ge=1.0, le=5.0)


class BraveSearchConfig(BaseModel):
    """Brave Search API configuration."""
    api_key: SecretStr = Field(..., description="Brave Search API key")
    base_url: str = Field(default="https://api.search.brave.com/res/v1/web/search")
    
    # Search parameters
    result_count: int = Field(default=10, ge=1, le=20)
    search_timeout: int = Field(default=5, ge=1, le=30)
    include_ai_summary: bool = Field(default=True)
    
    # Rate limiting
    rate_limit_per_minute: int = Field(default=100, ge=1, le=500)
    
    # Retry configuration
    max_retries: int = Field(default=3, ge=0, le=10)
    retry_backoff_base: float = Field(default=2.0, ge=1.0, le=5.0)


class CacheConfig(BaseModel):
    """Cache configuration."""
    enabled: bool = Field(default=True)
    backend: str = Field(default="redis", pattern="^(redis|memory|sqlite)$")
    
    # Redis-specific
    redis_url: Optional[str] = Field(default=None)
    redis_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    
    # Memory cache specific
    max_size_mb: int = Field(default=100, ge=10, le=1000)
    
    # Cache key settings
    max_cache_keys: int = Field(default=1000, ge=100, le=10000)
    
    @validator("redis_url")
    def validate_redis_url(cls, v, values):
        if values.get("backend") == "redis" and not v:
            raise ValueError("redis_url is required when backend is 'redis'")
        return v


class MonitoringConfig(BaseModel):
    """Monitoring and metrics configuration."""
    enabled: bool = Field(default=True)
    
    # Metrics export
    metrics_port: int = Field(default=9090, ge=1024, le=65535)
    metrics_path: str = Field(default="/metrics")
    
    # Health check
    health_check_port: int = Field(default=8080, ge=1024, le=65535)
    health_check_path: str = Field(default="/health")
    
    # Tracing
    tracing_enabled: bool = Field(default=False)
    tracing_endpoint: Optional[str] = Field(default=None)
    tracing_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)
    
    # Sentry error tracking
    sentry_dsn: Optional[SecretStr] = Field(default=None)
    sentry_environment: Optional[str] = Field(default=None)
    sentry_traces_sample_rate: float = Field(default=0.1, ge=0.0, le=1.0)


class SecurityConfig(BaseModel):
    """Security configuration."""
    # Input validation
    max_message_length: int = Field(default=1000, ge=100, le=5000)
    allowed_channels_regex: Optional[str] = Field(default=None)
    blocked_users: List[str] = Field(default_factory=list)
    
    # API key rotation
    enable_key_rotation: bool = Field(default=False)
    key_rotation_interval_days: int = Field(default=90, ge=1, le=365)
    
    # Request signing
    verify_slack_signatures: bool = Field(default=True)
    slack_signing_secret: Optional[SecretStr] = Field(default=None)
    
    @validator("slack_signing_secret")
    def validate_signing_secret(cls, v, values):
        if values.get("verify_slack_signatures") and not v:
            raise ValueError("slack_signing_secret is required when verify_slack_signatures is True")
        return v


class FeatureFlags(BaseModel):
    """Feature flags for gradual rollout."""
    enable_streaming_responses: bool = Field(default=False)
    enable_conversation_history: bool = Field(default=True)
    enable_suggested_prompts: bool = Field(default=True)
    enable_source_citations: bool = Field(default=True)
    max_sources_to_show: int = Field(default=3, ge=1, le=10)
    
    # Experimental features
    enable_multi_language_support: bool = Field(default=False)
    enable_custom_knowledge_base: bool = Field(default=False)


class Config(BaseModel):
    """Main configuration class."""
    # Environment
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    debug: bool = Field(default=False)
    log_level: LogLevel = Field(default=LogLevel.INFO)
    
    # Application info
    app_name: str = Field(default="Dataiku Agent")
    app_version: str = Field(default="1.0.0")
    
    # Component configs
    slack: SlackConfig
    openai: OpenAIConfig
    brave_search: BraveSearchConfig
    cache: CacheConfig = Field(default_factory=CacheConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    features: FeatureFlags = Field(default_factory=FeatureFlags)
    
    # Paths
    data_dir: Path = Field(default=Path("./data"))
    log_dir: Path = Field(default=Path("./logs"))
    
    @validator("debug")
    def set_debug_from_env(cls, v, values):
        """Set debug mode based on environment."""
        if values.get("environment") == Environment.DEVELOPMENT:
            return True
        return v
    
    @validator("log_level")
    def set_log_level_from_debug(cls, v, values):
        """Set log level based on debug mode."""
        if values.get("debug"):
            return LogLevel.DEBUG
        return v
    
    class Config:
        """Pydantic config."""
        case_sensitive = False
        env_prefix = "DATAIKU_AGENT_"
        env_nested_delimiter = "__"


def load_config_from_env() -> Config:
    """Load configuration from environment variables."""
    return Config(
        environment=Environment(os.getenv("ENVIRONMENT", "development")),
        slack=SlackConfig(
            bot_token=os.environ["SLACK_BOT_TOKEN"],
            app_token=os.environ["SLACK_APP_TOKEN"],
        ),
        openai=OpenAIConfig(
            api_key=os.environ["OPENAI_API_KEY"],
            reasoning_effort=ReasoningEffort(
                os.getenv("O3_REASONING_EFFORT", "medium")
            ),
        ),
        brave_search=BraveSearchConfig(
            api_key=os.environ["BRAVE_API_KEY"],
        ),
    )


def load_config_from_file(config_path: Path) -> Config:
    """Load configuration from JSON file."""
    with open(config_path, "r") as f:
        config_data = json.load(f)
    return Config(**config_data)


def get_config(config_path: Optional[Path] = None) -> Config:
    """
    Get configuration from file or environment.
    
    Args:
        config_path: Optional path to config file. If not provided,
                    loads from environment variables.
    
    Returns:
        Validated configuration object.
    """
    if config_path and config_path.exists():
        return load_config_from_file(config_path)
    return load_config_from_env()


# Global config instance (lazy loaded)
_config: Optional[Config] = None


def get_current_config() -> Config:
    """Get the current configuration instance."""
    global _config
    if _config is None:
        _config = get_config()
    return _config


def reload_config(config_path: Optional[Path] = None) -> Config:
    """Reload configuration from file or environment."""
    global _config
    _config = get_config(config_path)
    return _config 