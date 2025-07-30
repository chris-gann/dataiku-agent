"""
Cache service for Dataiku Agent.

This module provides caching functionality with support for multiple
backends (Redis, in-memory, SQLite) to improve performance and reduce
API calls.
"""
import json
import hashlib
import time
from abc import ABC, abstractmethod
from typing import Optional, Any, Dict, List
from datetime import datetime, timedelta

from ..core.config import CacheConfig
from ..core.exceptions import CacheError, CacheConnectionError, CacheOperationError
from ..core.logging import get_logger

logger = get_logger(__name__)


class CacheBackend(ABC):
    """Abstract base class for cache backends."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete value from cache."""
        pass
    
    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass
    
    @abstractmethod
    def clear(self) -> bool:
        """Clear all cache entries."""
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """Check if cache backend is healthy."""
        pass


class RedisBackend(CacheBackend):
    """Redis cache backend."""
    
    def __init__(self, redis_url: str, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        
        try:
            import redis
            self.redis_client = redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5,
            )
            # Test connection
            self.redis_client.ping()
            logger.info("redis_cache_connected", url=redis_url)
        except ImportError:
            raise CacheConnectionError("redis-py is not installed. Install with: pip install redis")
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise CacheConnectionError(f"Failed to connect to Redis: {str(e)}")
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from Redis."""
        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            logger.error("redis_get_error", key=key, error=str(e))
            raise CacheOperationError(f"Failed to get from cache: {str(e)}")
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in Redis with TTL."""
        try:
            serialized = json.dumps(value)
            ttl = ttl or self.ttl_seconds
            return bool(self.redis_client.setex(key, ttl, serialized))
        except Exception as e:
            logger.error("redis_set_error", key=key, error=str(e))
            raise CacheOperationError(f"Failed to set in cache: {str(e)}")
    
    def delete(self, key: str) -> bool:
        """Delete value from Redis."""
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error("redis_delete_error", key=key, error=str(e))
            raise CacheOperationError(f"Failed to delete from cache: {str(e)}")
    
    def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error("redis_exists_error", key=key, error=str(e))
            return False
    
    def clear(self) -> bool:
        """Clear all cache entries."""
        try:
            self.redis_client.flushdb()
            return True
        except Exception as e:
            logger.error("redis_clear_error", error=str(e))
            raise CacheOperationError(f"Failed to clear cache: {str(e)}")
    
    def health_check(self) -> bool:
        """Check if Redis is healthy."""
        try:
            return self.redis_client.ping()
        except Exception:
            return False


class InMemoryBackend(CacheBackend):
    """In-memory cache backend with TTL support."""
    
    def __init__(self, max_size_mb: int = 100, max_entries: int = 1000):
        self.max_size_mb = max_size_mb
        self.max_entries = max_entries
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._access_times: Dict[str, float] = {}
    
    def _cleanup_expired(self):
        """Remove expired entries."""
        now = time.time()
        expired_keys = [
            key for key, data in self._cache.items()
            if data.get("expires_at") and data["expires_at"] < now
        ]
        for key in expired_keys:
            del self._cache[key]
            self._access_times.pop(key, None)
    
    def _enforce_size_limit(self):
        """Enforce size limits using LRU eviction."""
        if len(self._cache) > self.max_entries:
            # Sort by access time and remove oldest
            sorted_keys = sorted(self._access_times.items(), key=lambda x: x[1])
            for key, _ in sorted_keys[:len(self._cache) - self.max_entries]:
                del self._cache[key]
                del self._access_times[key]
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from memory."""
        self._cleanup_expired()
        
        if key not in self._cache:
            return None
        
        data = self._cache[key]
        self._access_times[key] = time.time()
        
        return data["value"]
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in memory with optional TTL."""
        self._cleanup_expired()
        
        expires_at = None
        if ttl:
            expires_at = time.time() + ttl
        
        self._cache[key] = {
            "value": value,
            "expires_at": expires_at,
            "created_at": time.time(),
        }
        self._access_times[key] = time.time()
        
        self._enforce_size_limit()
        return True
    
    def delete(self, key: str) -> bool:
        """Delete value from memory."""
        if key in self._cache:
            del self._cache[key]
            self._access_times.pop(key, None)
            return True
        return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in memory."""
        self._cleanup_expired()
        return key in self._cache
    
    def clear(self) -> bool:
        """Clear all cache entries."""
        self._cache.clear()
        self._access_times.clear()
        return True
    
    def health_check(self) -> bool:
        """In-memory cache is always healthy."""
        return True


class CacheService:
    """Main cache service that manages backends and provides caching functionality."""
    
    def __init__(self, config: CacheConfig):
        self.config = config
        self.enabled = config.enabled
        self._backend: Optional[CacheBackend] = None
        
        if self.enabled:
            self._backend = self._create_backend()
    
    def _create_backend(self) -> CacheBackend:
        """Create the appropriate cache backend."""
        if self.config.backend == "redis":
            if not self.config.redis_url:
                raise CacheConnectionError("Redis URL is required for Redis backend")
            return RedisBackend(
                self.config.redis_url,
                self.config.redis_ttl_seconds,
            )
        elif self.config.backend == "memory":
            return InMemoryBackend(
                self.config.max_size_mb,
                self.config.max_cache_keys,
            )
        else:
            raise ValueError(f"Unsupported cache backend: {self.config.backend}")
    
    def _generate_key(self, prefix: str, params: Dict[str, Any]) -> str:
        """Generate a cache key from prefix and parameters."""
        # Sort params for consistent key generation
        sorted_params = sorted(params.items())
        param_str = json.dumps(sorted_params, sort_keys=True)
        
        # Create hash for long keys
        hash_obj = hashlib.sha256(param_str.encode())
        hash_str = hash_obj.hexdigest()[:16]
        
        return f"{prefix}:{hash_str}"
    
    def get_search_results(
        self,
        query: str,
        context: Optional[str] = None,
    ) -> Optional[List[Dict[str, Any]]]:
        """Get cached search results."""
        if not self.enabled or not self._backend:
            return None
        
        key = self._generate_key("search", {
            "query": query,
            "context": context,
        })
        
        try:
            result = self._backend.get(key)
            if result:
                logger.info("cache_hit", cache_type="search", query=query)
            return result
        except CacheError:
            # Log error but don't fail the request
            logger.warning("cache_get_failed", cache_type="search")
            return None
    
    def set_search_results(
        self,
        query: str,
        results: List[Dict[str, Any]],
        context: Optional[str] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache search results."""
        if not self.enabled or not self._backend:
            return False
        
        key = self._generate_key("search", {
            "query": query,
            "context": context,
        })
        
        try:
            return self._backend.set(key, results, ttl)
        except CacheError:
            logger.warning("cache_set_failed", cache_type="search")
            return False
    
    def get_synthesis(
        self,
        query: str,
        search_results_hash: str,
    ) -> Optional[str]:
        """Get cached synthesis result."""
        if not self.enabled or not self._backend:
            return None
        
        key = self._generate_key("synthesis", {
            "query": query,
            "results_hash": search_results_hash,
        })
        
        try:
            result = self._backend.get(key)
            if result:
                logger.info("cache_hit", cache_type="synthesis", query=query)
            return result
        except CacheError:
            logger.warning("cache_get_failed", cache_type="synthesis")
            return None
    
    def set_synthesis(
        self,
        query: str,
        search_results_hash: str,
        synthesis: str,
        ttl: Optional[int] = None,
    ) -> bool:
        """Cache synthesis result."""
        if not self.enabled or not self._backend:
            return False
        
        key = self._generate_key("synthesis", {
            "query": query,
            "results_hash": search_results_hash,
        })
        
        try:
            return self._backend.set(key, synthesis, ttl)
        except CacheError:
            logger.warning("cache_set_failed", cache_type="synthesis")
            return False
    
    def hash_search_results(self, results: List[Dict[str, Any]]) -> str:
        """Generate a hash of search results for cache key generation."""
        # Extract only relevant fields for hashing
        simplified = [
            {
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "snippet": r.get("snippet", "")[:100],  # First 100 chars
            }
            for r in results
        ]
        
        content = json.dumps(simplified, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def clear_expired(self) -> int:
        """Clear expired cache entries (backend-specific implementation)."""
        if not self.enabled or not self._backend:
            return 0
        
        # This is backend-specific
        # For Redis, TTL is handled automatically
        # For in-memory, cleanup happens on access
        return 0
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self.enabled:
            return {"enabled": False}
        
        stats = {
            "enabled": True,
            "backend": self.config.backend,
            "healthy": self._backend.health_check() if self._backend else False,
        }
        
        # Add backend-specific stats if available
        if isinstance(self._backend, InMemoryBackend):
            stats.update({
                "entries": len(self._backend._cache),
                "max_entries": self._backend.max_entries,
            })
        
        return stats
    
    def health_check(self) -> bool:
        """Check if cache is healthy."""
        if not self.enabled:
            return True  # Disabled cache is "healthy"
        
        return self._backend.health_check() if self._backend else False 