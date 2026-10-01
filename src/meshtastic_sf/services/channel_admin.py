"""PKI-authorized channel registration. Never log command bodies or echo keys."""
import base64
import hmac
from collections import deque
from ..domain.channel_crypto import parse_channel


class ChannelAdmin:
    def __init__(self,repository):
        self.repository=repository
        self.replies=deque(maxlen=8)

    def accept(self,frame,ingestor):
        if not ingestor.ready or not frame.HasField('packet'): return
        p=frame.packet
        if p.WhichOneof('payload_variant')!='decoded' or p.decoded.portnum!=1: return
        parts=p.decoded.payload.decode('utf-8',errors='replace').strip().split()
        if not parts or parts[0].casefold()!='/channel': return
        server=int(ingestor.device.split(':')[0],16)
        if not p.pki_encrypted or p.via_mqtt or p.to!=server or not p.id or not 0<getattr(p,'from')<0xffffffff or getattr(p,'from')==server or len(p.public_key)!=32: return
        policy=self.repository.catalog.remote_policy()
        key=base64.b64encode(p.public_key).decode()
        if not policy['enabled'] or not any(hmac.compare_digest(key,k) for k in policy['public_keys']): return
        if len(self.replies)>=self.replies.maxlen: return
        if not self.repository.catalog.claim_remote_request(p.public_key,p.id): return
        response='Usage: /channel add NAME BASE64_KEY'
        if len(p.decoded.payload)<=180 and len(parts)==4 and parts[1].casefold()=='add':
            try:
                name,psk=parse_channel(parts[2],parts[3])
                self.repository.catalog.save(name,psk,capture=True,replay=False)
                response='Channel added. Capture on; history sharing off. Configure sharing in MeshMemo.'
            except ValueError:
                response='Channel not added: invalid channel/key, duplicate or catalogue full.'
        self.replies.append((getattr(p,'from'),bytes(p.public_key),response))

    def tick(self,radio):
        if self.replies:
            recipient,key,text=self.replies.popleft()
            radio.send_admin_receipt(recipient,key,text)
