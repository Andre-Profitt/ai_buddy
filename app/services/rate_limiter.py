import redis.asyncio as redis
from app.core.config import settings
import time

class RateLimiter:
    def __init__(self):
        self.redis = redis.from_url(f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}", encoding="utf-8", decode_responses=True)
        
        # Limits
        self.GROUP_LIMIT_PER_HOUR = 10
        self.USER_LIMIT_PER_DAY = 20

    async def is_allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        """
        Generic sliding window or fixed window rate limiter.
        Using simple fixed window for MVP.
        """
        current_window = int(time.time() / window_seconds)
        redis_key = f"rate_limit:{key}:{current_window}"
        
        current_count = await self.redis.incr(redis_key)
        if current_count == 1:
            await self.redis.expire(redis_key, window_seconds)
            
        return current_count <= limit

    async def check_group_limit(self, group_id: str) -> bool:
        return await self.is_allowed(f"group:{group_id}", self.GROUP_LIMIT_PER_HOUR, 3600)

    async def check_user_limit(self, user_id: str) -> bool:
        return await self.is_allowed(f"user:{user_id}", self.USER_LIMIT_PER_DAY, 86400)

rate_limiter = RateLimiter()
