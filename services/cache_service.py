import redis
import json
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timedelta
import hashlib

logger = logging.getLogger(__name__)

class CacheService:
    """Redis-based caching service for quiz data and performance optimization"""
    
    def __init__(self, host: str = 'localhost', port: int = 6379, db: int = 0):
        try:
            self.redis_client = redis.Redis(
                host=host, 
                port=port, 
                db=db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            self.redis_client.ping()
            logger.info(f"Redis cache connected successfully to {host}:{port}")
        except redis.ConnectionError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self.redis_client = None
        except Exception as e:
            logger.error(f"Redis initialization error: {e}")
            self.redis_client = None
    
    def cache_quiz(self, quiz_id: str, quiz_data: Dict[str, Any], ttl: int = 3600) -> bool:
        """Cache quiz data with TTL (default 1 hour)"""
        if not self.redis_client:
            return False
        
        try:
            key = f"quiz:{quiz_id}"
            value = json.dumps(quiz_data, default=str)
            self.redis_client.setex(key, ttl, value)
            logger.info(f"Cached quiz {quiz_id} with TTL {ttl}s")
            return True
        except Exception as e:
            logger.error(f"Failed to cache quiz {quiz_id}: {e}")
            return False
    
    def get_cached_quiz(self, quiz_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached quiz data"""
        if not self.redis_client:
            return None
        
        try:
            key = f"quiz:{quiz_id}"
            cached = self.redis_client.get(key)
            if cached:
                logger.info(f"Cache hit for quiz {quiz_id}")
                return json.loads(cached)
            logger.info(f"Cache miss for quiz {quiz_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve cached quiz {quiz_id}: {e}")
            return None
    
    def cache_wikipedia_content(self, url: str, content_data: Dict[str, Any], ttl: int = 7200) -> bool:
        """Cache Wikipedia scraped content (default 2 hours)"""
        if not self.redis_client:
            return False
        
        try:
            url_hash = hashlib.md5(url.encode()).hexdigest()
            key = f"wikipedia:{url_hash}"
            value = json.dumps(content_data, default=str)
            self.redis_client.setex(key, ttl, value)
            logger.info(f"Cached Wikipedia content for {url} with TTL {ttl}s")
            return True
        except Exception as e:
            logger.error(f"Failed to cache Wikipedia content for {url}: {e}")
            return False
    
    def get_cached_wikipedia_content(self, url: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached Wikipedia content"""
        if not self.redis_client:
            return None
        
        try:
            url_hash = hashlib.md5(url.encode()).hexdigest()
            key = f"wikipedia:{url_hash}"
            cached = self.redis_client.get(key)
            if cached:
                logger.info(f"Cache hit for Wikipedia content {url}")
                return json.loads(cached)
            logger.info(f"Cache miss for Wikipedia content {url}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve cached Wikipedia content for {url}: {e}")
            return None
    
    def cache_quiz_list(self, user_id: str, quiz_payload: Dict[str, Any], ttl: int = 300) -> bool:
        """Cache paginated quiz list metadata for user (default 5 minutes)"""
        if not self.redis_client:
            return False
        
        try:
            key = f"user_quizzes:{user_id}"
            value = json.dumps(quiz_payload, default=str)
            self.redis_client.setex(key, ttl, value)
            logger.info(f"Cached quiz list for user {user_id} with TTL {ttl}s")
            return True
        except Exception as e:
            logger.error(f"Failed to cache quiz list for user {user_id}: {e}")
            return False
    
    def get_cached_quiz_list(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve cached quiz list for user"""
        if not self.redis_client:
            return None
        
        try:
            key = f"user_quizzes:{user_id}"
            cached = self.redis_client.get(key)
            if cached:
                logger.info(f"Cache hit for user quiz list {user_id}")
                return json.loads(cached)
            logger.info(f"Cache miss for user quiz list {user_id}")
            return None
        except Exception as e:
            logger.error(f"Failed to retrieve cached quiz list for user {user_id}: {e}")
            return None
    
    def increment_rate_limit(self, identifier: str, limit: int = 10, window: int = 3600) -> bool:
        """Increment rate limit counter (default: 10 requests per hour)"""
        if not self.redis_client:
            return True
        
        try:
            key = f"rate_limit:{identifier}"
            current = self.redis_client.incr(key)
            if current == 1:
                self.redis_client.expire(key, window)
            
            if current > limit:
                logger.warning(f"Rate limit exceeded for {identifier}: {current}/{limit}")
                return False
            
            logger.info(f"Rate limit check passed for {identifier}: {current}/{limit}")
            return True
        except Exception as e:
            logger.error(f"Rate limit check failed for {identifier}: {e}")
            return True 
    
    def get_rate_limit_status(self, identifier: str) -> Dict[str, Any]:
        """Get current rate limit status"""
        if not self.redis_client:
            return {"allowed": True, "current": 0, "limit": 10, "remaining": 10}
        
        try:
            key = f"rate_limit:{identifier}"
            current = int(self.redis_client.get(key) or 0)
            ttl = self.redis_client.ttl(key)
            limit = 10
            
            return {
                "allowed": current <= limit,
                "current": current,
                "limit": limit,
                "remaining": max(0, limit - current),
                "resets_in": ttl if ttl > 0 else 3600
            }
        except Exception as e:
            logger.error(f"Failed to get rate limit status for {identifier}: {e}")
            return {"allowed": True, "current": 0, "limit": 10, "remaining": 10}
    
    def clear_cache(self, pattern: str = "*") -> bool:
        """Clear cache entries matching pattern"""
        if not self.redis_client:
            return False
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
                logger.info(f"Cleared {len(keys)} cache entries matching '{pattern}'")
            return True
        except Exception as e:
            logger.error(f"Failed to clear cache for pattern '{pattern}': {e}")
            return False
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        if not self.redis_client:
            return {"status": "disconnected", "stats": {}}
        
        try:
            info = self.redis_client.info()
            return {
                "status": "connected",
                "stats": {
                    "total_keys": self.redis_client.dbsize(),
                    "used_memory": info.get("used_memory_human", "N/A"),
                    "connected_clients": info.get("connected_clients", 0),
                    "total_commands_processed": info.get("total_commands_processed", 0),
                    "keyspace_hits": info.get("keyspace_hits", 0),
                    "keyspace_misses": info.get("keyspace_misses", 0),
                    "hit_rate": f"{(info.get('keyspace_hits', 0) / max(1, info.get('keyspace_hits', 0) + info.get('keyspace_misses', 0)) * 100):.1f}%"
                }
            }
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"status": "error", "stats": {}}


cache_service = None

def get_cache_service() -> CacheService:
    """Get or create the global cache service instance"""
    global cache_service
    if cache_service is None:
        cache_service = CacheService()
    return cache_service
