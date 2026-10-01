"""Password-protected administration; settings never mutate radio configuration."""

import asyncio
from contextlib import asynccontextmanager
from importlib.resources import files
from pathlib import Path
import secrets
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from ..services.runtime import ServerRuntime
from ..services.ownership import ArchiveOwner
from ..storage.repository import HistoryRepository
from .auth import AdminAuth


class SettingsInput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    max_records: int = Field(ge=1, le=10_000_000)
    dedupe_seconds: int = Field(ge=1, le=604800)
    retention_days: int = Field(ge=0, le=3650)
    capture_enabled: StrictBool
    replay_enabled: StrictBool = False
    replay_limit: int = Field(default=20,ge=1,le=100)
    replay_window_minutes: int = Field(default=1440,ge=1,le=10080)
    replay_max_window_minutes: int = Field(default=10080,ge=1,le=10080)
    replay_interval_seconds: int = Field(default=5,ge=5,le=60)
    replay_cooldown_seconds: int = Field(default=60,ge=30,le=3600)
    replay_heartbeat_seconds: int = Field(default=900,ge=900,le=86400)
    replay_heartbeat_enabled: StrictBool = True
    confirm_retention: StrictBool = False

    @model_validator(mode='after')
    def check_window(self):
        if self.replay_window_minutes > self.replay_max_window_minutes:
            raise ValueError('Окно по умолчанию должно быть не больше максимального')
        return self


class ConnectionInput(BaseModel):
    model_config = ConfigDict(extra='forbid',strict=True)
    mode: str = Field(pattern='^(off|auto|manual)$')
    port: str = Field(default='',max_length=256)


class CatalogInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    name: str = Field(default='', max_length=64)
    key: str = Field(default='', max_length=128)
    link: str = Field(default='', max_length=2048)
    capture: StrictBool = True
    replay: StrictBool = False
    channel_id: int | None = Field(default=None, ge=1)


class CatalogPolicyInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    capture: StrictBool
    replay: StrictBool


class ChannelAdminInput(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    enabled: StrictBool
    public_keys: list[str] = Field(max_length=8)


def create_app(database: str, device: str | None = None, *, admin_password: str,
               allowed_hosts=("127.0.0.1", "localhost", "[::1]"), allow_remote=False,
               runtime_factory=ServerRuntime):
    auth = AdminAuth(admin_password)
    csrf = secrets.token_urlsafe(32)
    root = Path(str(files("meshtastic_sf.web")))
    templates = Jinja2Templates(directory=str(root / "templates"))

    @asynccontextmanager
    async def lifespan(app):
        with ArchiveOwner(database):
            repository = HistoryRepository(database)
            runtime = None
            try:
                runtime = runtime_factory(repository, device)
                app.state.repository, app.state.runtime = repository, runtime
                runtime.start()
                yield
            finally:
                try:
                    if runtime is not None:
                        await asyncio.to_thread(runtime.stop)
                finally:
                    repository.close()

    app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts))

    @app.middleware("http")
    async def protect(request, call_next):
        response = None
        if not allow_remote and request.client and request.client.host not in {"127.0.0.1", "::1", "testclient"}:
            response = JSONResponse({"detail": "Local access only"}, status_code=403)
        if response is None:
            response = auth.reject(request)
        if response is None and request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if (not secrets.compare_digest(request.headers.get("x-csrf-token", ""), csrf)
                    or (origin and origin != str(request.base_url).rstrip("/"))):
                response = JSONResponse({"detail": "Invalid request token or origin"}, status_code=403)
        if response is None:
            response = await call_next(request)
        response.headers.update({"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                                 "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; form-action 'self'; object-src 'none'"})
        return response

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # FastAPI's default includes submitted values, including PSKs and channel links.
        return JSONResponse({'detail': 'Некорректные настройки. Проверьте значения полей.'}, status_code=422)

    @app.exception_handler(Exception)
    async def internal_error(request, exc):
        return JSONResponse({"detail": "Операция не выполнена. Проверьте доступ к базе и место на диске."}, status_code=500)

    app.mount("/static", StaticFiles(directory=root / "static"), name="static")

    @app.get("/")
    def index(request: Request):
        return templates.TemplateResponse(request=request, name="index.html", context={"csrf": csrf})

    @app.get("/healthz")
    def health(request: Request):
        # Liveness is distinct from USB connectivity and archive integrity.
        thread = request.app.state.runtime.thread
        alive = thread is not None and thread.is_alive()
        return JSONResponse({"status": "ok" if alive else "degraded"}, status_code=200 if alive else 503)

    @app.get("/api/status")
    def status(request: Request):
        return {"runtime": request.app.state.runtime.snapshot(), "database": request.app.state.repository.summary(),
                "settings": request.app.state.repository.get_settings(),
                "connection": {k:v for k,v in request.app.state.repository.get_connection().items() if k not in {'identity','configured'}}}

    @app.get('/api/ports')
    def ports(request: Request):
        return request.app.state.runtime.ports()

    @app.post('/api/connection')
    def change_connection(request: Request, values: ConnectionInput):
        runtime = request.app.state.runtime
        if values.mode=='manual' and values.port not in {p['device'] for p in runtime.ports()}:
            raise HTTPException(409,'Выбранный порт недоступен. Обновите список устройств.')
        runtime.repository.set_connection(values.mode,values.port)
        runtime.reconnect()
        return {'mode':values.mode,'port':values.port}

    @app.get('/api/channel-catalog')
    def catalog_list(request: Request):
        return request.app.state.repository.catalog.public()

    @app.post('/api/channel-catalog')
    def catalog_save(request: Request, values: CatalogInput):
        from ..domain.channel_crypto import parse_channel
        runtime = request.app.state.runtime
        try:
            with runtime.replay.lock:
                if values.channel_id is not None and not values.key and not values.link:
                    existing=next((entry for entry in runtime.repository.catalog.entries() if entry['id']==values.channel_id),None)
                    if existing is None:
                        raise ValueError('Channel not found')
                    name,key=values.name,existing['key']
                else:
                    name, key = parse_channel(values.name, values.key, values.link)
                channel_id = runtime.repository.catalog.save(name, key, values.capture, values.replay, values.channel_id)
                runtime.replay.cancel()
            return {'id': channel_id}
        except ValueError:
            raise HTTPException(422, 'Не удалось сохранить канал. Проверьте имя, ключ и отсутствие дубликата.') from None

    @app.post('/api/channel-catalog/{channel_id}/policy')
    def catalog_policy(request: Request, channel_id: int, values: CatalogPolicyInput):
        runtime = request.app.state.runtime
        try:
            with runtime.replay.lock:
                runtime.repository.catalog.policy(channel_id, values.capture, values.replay)
                runtime.replay.cancel()
            return {'saved': True}
        except ValueError:
            raise HTTPException(404, 'Канал не найден') from None

    @app.get('/api/channel-admin')
    def channel_admin_policy(request: Request):
        return request.app.state.repository.catalog.remote_policy()

    @app.post('/api/channel-admin')
    def channel_admin_save(request: Request, values: ChannelAdminInput):
        try:
            return request.app.state.repository.catalog.set_remote_policy(values.enabled, values.public_keys)
        except ValueError:
            raise HTTPException(422, 'Проверьте публичные ключи администраторов') from None

    @app.get("/api/channels")
    def channel_list(request: Request):
        return request.app.state.repository.list_channels()

    @app.get("/api/messages")
    def message_list(request: Request, scope: str = Query(pattern="^[a-f0-9]{64}$"),
                     before: int | None = Query(default=None, ge=1), q: str = Query(default="", max_length=200)):
        return request.app.state.repository.chat(scope, before=before, query=q)

    @app.post("/api/settings")
    def change_settings(request: Request, values: SettingsInput):
        repository = request.app.state.repository
        previous = repository.get_settings()
        if values.retention_days and (not previous["retention_days"] or values.retention_days < previous["retention_days"]):
            if not values.confirm_retention:
                raise HTTPException(409, "Подтвердите удаление сообщений старше выбранного срока")
        runtime = request.app.state.runtime
        # Serialize disable with USB submission: after this response no further job packets can be submitted.
        with runtime.replay.lock:
            result = repository.update_settings(values.model_dump(exclude={"confirm_retention"}))
            if any(previous[k]!=result[k] for k in result if k.startswith('replay_')):
                runtime.replay.cancel("idle" if result['replay_enabled'] else "disabled")
                runtime.replay.next_heartbeat = 0
        request.app.state.runtime.event("Настройки сервера сохранены")
        return result

    @app.post("/api/integrity")
    def integrity(request: Request):
        return {"result": request.app.state.repository.integrity()}

    @app.post("/api/backup")
    def backup(request: Request):
        repository = request.app.state.repository
        directory = repository.path.parent / "backups"
        directory.mkdir(exist_ok=True)
        target = directory / f"history-{int(time.time())}-{secrets.token_hex(4)}.db"
        repository.backup(target)
        request.app.state.runtime.event("Создана резервная копия базы")
        return FileResponse(target, filename=target.name, media_type="application/vnd.sqlite3")

    return app
