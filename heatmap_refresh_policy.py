"""Throttle failed/partial sector snapshot refreshes without hiding cached rows."""
def needs_refresh(data, cache, now, ttl=300, retry_ttl=60):
    attempted = cache.get('lastAttempt', 0)
    if attempted and now - attempted < retry_ttl:
        return False
    if not data:
        return True
    age = now - cache.get('timestamp', 0)
    return age >= (ttl if data.get('complete') else retry_ttl)
