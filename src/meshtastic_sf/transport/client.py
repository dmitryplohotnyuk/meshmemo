"""Stop-and-wait requests with exact-token retries and fail-closed timeouts."""

from collections.abc import Callable
import secrets
import threading

from .protocol import Operation, ReplayMessage, Response, Status, header


class BridgeUnavailable(RuntimeError):
    pass


class BridgeRejected(RuntimeError):
    def __init__(self, response: Response):
        self.response = response
        super().__init__(f"Bridge rejected {response.operation.name}: {response.status.name}")


class BridgeClient:
    def __init__(self, exchange: Callable[[bytes, float], bytes], timeout: float = 5.0):
        self.exchange = exchange
        self.timeout = timeout
        self.session = secrets.randbelow(0xFFFFFFFF) + 1
        self.token = 0
        self.ready = False
        self.capabilities = None
        self.lock = threading.Lock()

    def _request(self, op: Operation, message: ReplayMessage | None = None) -> Response:
        if self.token == 0xFFFFFFFF:
            self.ready = False
            raise BridgeUnavailable("Session token space exhausted; reconnect")
        self.token += 1
        payload = message.encode(self.session, self.token) if message else header(op, self.session, self.token)
        for attempt in range(2):
            try:
                response = Response.decode(self.exchange(payload, self.timeout))
                break
            except TimeoutError as exc:
                if attempt:
                    self.ready = False
                    raise BridgeUnavailable("No bridge response; outcome unknown, reconnect before continuing") from exc
            except (ValueError, OSError) as exc:
                self.ready = False
                raise BridgeUnavailable("Invalid bridge response or transport failure") from exc
        if (response.operation, response.session, response.token) != (op, self.session, self.token):
            self.ready = False
            raise BridgeUnavailable("Mismatched bridge response")
        try:
            self.validate_capabilities(response)
            if self.ready and self.capabilities != response.capability_identity:
                raise ValueError("Bridge capabilities changed during the session; reconnect")
        except ValueError as exc:
            self.ready = False
            raise BridgeUnavailable(str(exc)) from exc
        if response.status != Status.OK:
            if response.status in (Status.SESSION, Status.STALE, Status.CONFLICT, Status.UNSUPPORTED):
                self.ready = False
            raise BridgeRejected(response)
        return response

    def validate_capabilities(self, response):
        response.require_compatible()

    def connect(self) -> Response:
        with self.lock:
            self.ready = False
            response = self._request(Operation.HELLO)
            self.capabilities = response.capability_identity
            self.ready = True
            return response

    def replay(self, message: ReplayMessage) -> Response:
        with self.lock:
            if not self.ready:
                raise BridgeUnavailable("Capability handshake required")
            raise BridgeUnavailable("Replay disabled: encrypted packet identity is unresolved (diagnostic profile 0)")

    def abort(self) -> Response:
        with self.lock:
            if not self.ready:
                raise BridgeUnavailable("Capability handshake required")
            return self._request(Operation.ABORT)
