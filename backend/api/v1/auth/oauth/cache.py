# api/v1/auth/oauth/cache.py

import time

class OAuthTTLCache:
    def __init__(self, ttl_seconds: int):
        self.ttl = ttl_seconds
        self._data = {}

    def get(self, key: str):
        item = self._data.get(key)
        if not item:
            return None
        value, expires_at = item
        if expires_at < time.time():
            del self._data[key]
            return None
        return value

    def set(self, key: str, value):
        self._data[key] = (value, time.time() + self.ttl)

    def delete(self, key: str):
        if key in self._data:
            del self._data[key]