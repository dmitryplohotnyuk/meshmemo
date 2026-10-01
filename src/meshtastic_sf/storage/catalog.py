"""Secret-bearing catalogue. Public projections never contain PSKs or ciphertext."""
import base64
import hashlib
import json
import os
from pathlib import Path
import threading
import time
import sqlalchemy as sa
from cryptography.fernet import Fernet
from .models import catalog,admin_policy,admin_requests
from ..domain.channel_crypto import validate_key


class ChannelCatalog:
    MAX_CHANNELS=256
    def __init__(self,repository):
        self.repository=repository
        self.lock=threading.RLock()
        self.revision=0
        self.key_path=Path(str(repository.path)+'.channels.key')
        self._fernet=None
        self._cache=None
        # Never silently replace a lost master key when encrypted records exist.
        with repository.engine.connect() as c:
            has_entries=c.execute(sa.select(sa.func.count()).select_from(catalog)).scalar_one()>0
        if has_entries:
            self._vault(create=False)
            self.entries()

    def _vault(self,create=False):
        if self._fernet is None:
            if self.key_path.is_symlink():
                raise ValueError('Channel key file must not be a symlink')
            if not self.key_path.exists() and create:
                fd=os.open(self.key_path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
                with os.fdopen(fd,'wb') as f:
                    f.write(Fernet.generate_key()); f.flush(); os.fsync(f.fileno())
            if os.name!='nt' and self.key_path.stat().st_mode & 0o077:
                raise ValueError('Channel key file requires mode 0600')
            self._fernet=Fernet(self.key_path.read_bytes())
        return self._fernet

    def public(self):
        with self.repository.engine.connect() as c:
            return [dict(r) for r in c.execute(sa.select(catalog.c.id,catalog.c.name,catalog.c.capture,catalog.c.replay,catalog.c.last_seen).order_by(catalog.c.id)).mappings()]

    def entries(self):
        with self.lock:
            if self._cache is None:
                with self.repository.engine.connect() as c:
                    rows=c.execute(sa.select(catalog)).mappings().all()
                self._cache=[{**dict(r),'key':self._vault().decrypt(r['key_ciphertext'])} for r in rows]
            return self._cache

    def save(self,name,key,capture=True,replay=False,channel_id=None):
        validate_key(name,key)
        if type(capture)!=bool or type(replay)!=bool:
            raise ValueError('Invalid channel policy')
        with self.lock:
            identity=hashlib.sha256(name.encode()+b'\0'+key).hexdigest()
            encrypted=self._vault(create=True).encrypt(key)
            with self.repository.engine.begin() as c:
                duplicate=c.execute(sa.select(catalog.c.id).where(catalog.c.identity==identity)).scalar_one_or_none()
                if duplicate is not None and duplicate!=channel_id:
                    raise ValueError('Channel is already registered')
                if channel_id is None:
                    if c.execute(sa.select(sa.func.count()).select_from(catalog)).scalar_one()>=self.MAX_CHANNELS:
                        raise ValueError('Channel catalogue is full')
                    channel_id=c.execute(catalog.insert().values(name=name,key_ciphertext=encrypted,identity=identity,capture=capture,replay=replay)).inserted_primary_key[0]
                else:
                    updates=dict(name=name,key_ciphertext=encrypted,identity=identity,capture=capture,replay=replay)
                    if duplicate!=channel_id:
                        updates['last_seen']=None
                    result=c.execute(catalog.update().where(catalog.c.id==channel_id).values(**updates))
                    if not result.rowcount: raise ValueError('Channel not found')
            self.revision+=1; self._cache=None
            return channel_id

    def policy(self,channel_id,capture,replay):
        if type(capture)!=bool or type(replay)!=bool: raise ValueError('Invalid channel policy')
        with self.lock,self.repository.engine.begin() as c:
            if not c.execute(catalog.update().where(catalog.c.id==channel_id).values(capture=capture,replay=replay)).rowcount:
                raise ValueError('Channel not found')
            self.revision+=1; self._cache=None

    def seen(self,channel_id,at):
        with self.repository.engine.begin() as c:
            c.execute(catalog.update().where(catalog.c.id==channel_id).values(last_seen=at))

    def remote_policy(self):
        with self.repository.engine.connect() as c:
            row=c.execute(sa.select(admin_policy)).mappings().one()
        return {'enabled':row['enabled'],'public_keys':json.loads(row['public_keys'])}

    def set_remote_policy(self,enabled,keys):
        if type(enabled)!=bool or len(keys)>8: raise ValueError('Invalid administrator policy')
        try:
            keys=list(dict.fromkeys(keys))
            if any(len(base64.b64decode(k,validate=True))!=32 for k in keys) or (enabled and not keys): raise ValueError()
        except (ValueError,TypeError):
            raise ValueError('Provide administrator public keys in Base64') from None
        with self.repository.engine.begin() as c:
            c.execute(admin_policy.update().where(admin_policy.c.id==1).values(enabled=enabled,public_keys=json.dumps(keys)))
        return self.remote_policy()

    def claim_remote_request(self,public_key,packet_id):
        """Persist the replay guard before acting; a crash fails closed."""
        who=hashlib.sha256(public_key).hexdigest()
        identity=f'{who}:{packet_id}'
        now=int(time.time())
        with self.repository.engine.begin() as c:
            if c.execute(sa.select(admin_requests.c.identity).where(admin_requests.c.identity==identity)).first(): return False
            recent=c.execute(sa.select(admin_requests.c.identity).where(admin_requests.c.identity.startswith(who+':'),admin_requests.c.received_at>now-60)).first()
            if recent or c.execute(sa.select(sa.func.count()).select_from(admin_requests)).scalar_one()>=10000: return False
            c.execute(admin_requests.insert().values(identity=identity,received_at=now))
        return True
