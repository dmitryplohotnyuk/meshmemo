"""Single-operator HTTP Basic authentication with bounded failed-login throttling."""

import base64
import binascii
from collections import OrderedDict
import hashlib
import secrets
import time

from fastapi.responses import JSONResponse


class AdminAuth:
    def __init__(self, password: str):
        if not isinstance(password, str) or len(password.strip()) < 12:
            raise ValueError("An admin password of at least 12 characters is required")
        self.digest = hashlib.sha256(("admin:" + password).encode("utf-8")).digest()
        self.failures = OrderedDict()

    def reject(self, request):
        # Called synchronously on the event loop; no await between rate-limit updates.
        now = time.monotonic()
        key = request.client.host if request.client else "unknown"
        attempts, until = self.failures.get(key, (0, 0))
        if until <= now:
            attempts = 0
        if attempts >= 10:
            return JSONResponse({"detail": "Too many login attempts; retry in one minute"}, 429,
                                headers={"Retry-After": str(max(1, int(until - now) + 1))})
        header = request.headers.get("authorization", "")
        scheme, _, encoded = header.partition(" ")
        credentials = b""
        if scheme.lower() == "basic" and len(encoded) <= 4096:
            try:
                credentials = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                pass
        if secrets.compare_digest(hashlib.sha256(credentials).digest(), self.digest):
            self.failures.pop(key, None)
            return None
        # Browsers first request a challenge without credentials; don't count that as a guess.
        if header:
            self.failures[key] = (attempts + 1, until if attempts else now + 60)
            self.failures.move_to_end(key)
            if len(self.failures) > 1024:
                self.failures.popitem(last=False)
        return JSONResponse({"detail": "Admin login required"}, 401,
                            headers={"WWW-Authenticate": 'Basic realm="MeshMemo", charset="UTF-8"'})
