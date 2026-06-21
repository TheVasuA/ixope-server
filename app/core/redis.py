"""
Redis connection — used for:
  1. Session cache (user auth tokens)
  2. Real-time device status (heartbeat TTL)
  3. PDF generation job queue / image pre-cache
"""
import redis.asyncio as redis
from .config import settings

_redis_client = None


async def get_redis() -> redis.Redis:
    """Get or create async Redis connection."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    return _redis_client


async def close_redis():
    """Close Redis connection on shutdown."""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        _redis_client = None


# ─── Session Helpers ──────────────────────────────────────────────────────────

async def set_session(session_id: str, user_data: dict, ttl: int = 86400):
    """Store user session in Redis (default 24h TTL)."""
    r = await get_redis()
    import json
    await r.set(f"session:{session_id}", json.dumps(user_data), ex=ttl)


async def get_session(session_id: str) -> dict | None:
    """Retrieve user session from Redis."""
    r = await get_redis()
    import json
    data = await r.get(f"session:{session_id}")
    return json.loads(data) if data else None


async def delete_session(session_id: str):
    """Delete user session."""
    r = await get_redis()
    await r.delete(f"session:{session_id}")


# ─── Device Status Helpers ────────────────────────────────────────────────────

async def set_device_online(device_id: str, ip: str = "", ttl: int = 60):
    """Mark device as online with 60s TTL (auto-expires if no heartbeat)."""
    r = await get_redis()
    import json
    await r.set(
        f"device:{device_id}:status",
        json.dumps({"online": True, "ip": ip}),
        ex=ttl,
    )


async def is_device_online(device_id: str) -> bool:
    """Check if device is online (key exists = heartbeat received within TTL)."""
    r = await get_redis()
    return await r.exists(f"device:{device_id}:status") > 0


async def get_device_status(device_id: str) -> dict | None:
    """Get device real-time status from Redis."""
    r = await get_redis()
    import json
    data = await r.get(f"device:{device_id}:status")
    return json.loads(data) if data else None


# ─── PDF Image Pre-Cache ──────────────────────────────────────────────────────

async def cache_image_for_pdf(image_id: int, base64_data: str, ttl: int = 300):
    """Cache image base64 data for fast PDF generation (5 min TTL)."""
    r = await get_redis()
    await r.set(f"pdf:img:{image_id}", base64_data, ex=ttl)


async def get_cached_image(image_id: int) -> str | None:
    """Get pre-cached image for PDF generation."""
    r = await get_redis()
    return await r.get(f"pdf:img:{image_id}")


async def cache_selected_images(user_id: str, image_ids: list[int], ttl: int = 600):
    """Cache the user's selected image IDs for quick PDF generation (10 min)."""
    r = await get_redis()
    import json
    await r.set(f"pdf:selection:{user_id}", json.dumps(image_ids), ex=ttl)


async def get_selected_images(user_id: str) -> list[int] | None:
    """Get user's cached image selection."""
    r = await get_redis()
    import json
    data = await r.get(f"pdf:selection:{user_id}")
    return json.loads(data) if data else None
