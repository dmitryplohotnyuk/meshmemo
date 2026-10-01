"""Profile 1: new transport identity + original_id, scoped to current radio config."""
from dataclasses import dataclass
import hashlib
import struct
import queue
import threading

from .protocol import HEADER, REPLAY, BASE_COMMIT, Operation, Status, header, uint32
from .client import BridgeClient, BridgeUnavailable
from .capture import CaptureSerialInterface
from .serial import BridgeSerialInterface
from . import bridge_pb2
from meshtastic.protobuf import storeforward_pb2
from ..domain.replay import MAX_REPLAY_TEXT


def context_digest(channel: bytes, lora: bytes) -> bytes:
    return hashlib.sha256(struct.pack("<I", len(channel)) + channel + lora).digest()[:16]


@dataclass(frozen=True)
class FreshReplay:
    sender: int
    packet_id: int
    requester: int
    channel: int
    text: bytes
    outer_id: int
    context: bytes
    reply_id: int = 0
    emoji: bool = False

    def encode(self, session, token):
        for field in ("sender", "packet_id", "requester", "outer_id"):
            uint32(getattr(self, field), field, nonzero=True)
        if self.sender in (self.requester, 0xFFFFFFFF) or self.requester == 0xFFFFFFFF or self.outer_id == self.packet_id:
            raise ValueError("Invalid replay identity")
        if not 0 <= self.channel < 8 or len(self.context) != 16 or not 1 <= len(self.text) <= MAX_REPLAY_TEXT:
            raise ValueError("Invalid replay scope or size")
        uint32(self.reply_id, "reply_id")
        if type(self.emoji) is not bool:
            raise ValueError("Invalid emoji flag")
        self.text.decode("utf-8")
        return header(Operation.REPLAY, session, token) + REPLAY.pack(
            self.sender, self.packet_id, self.requester, self.channel, self.reply_id, self.emoji
        ) + struct.pack("<I", self.outer_id) + self.context + self.text


@dataclass(frozen=True)
class Control:
    requester: int
    channel: int
    outer_id: int
    context: bytes
    payload: bytes

    def encode(self, session, token):
        uint32(self.requester, "requester", nonzero=True)
        uint32(self.outer_id, "outer_id", nonzero=True)
        if not 0 <= self.channel < 8 or len(self.context) != 16 or not 1 <= len(self.payload) <= 100:
            raise ValueError("Invalid control packet")
        if self.requester == 0xFFFFFFFF and storeforward_pb2.StoreAndForward.FromString(self.payload).rr != 2:
            raise ValueError("Only discovery heartbeat can be broadcast")
        return header(Operation.CONTROL, session, token) + struct.pack("<III", self.requester, self.channel, self.outer_id) + self.context + self.payload


class ReplayBridgeClient(BridgeClient):
    def validate_capabilities(self, response):
        if response.protocol_version == 2:
            response.require_portable(1)
            return
        if (response.protocol_version != 1 or response.base_commit != BASE_COMMIT or response.profile != 1 or response.patch_revision not in (2, 3)
                or response.max_text != MAX_REPLAY_TEXT or response.hardware_model != 12):
            raise ValueError("Требуется совместимая MeshMemo-прошивка: USF1 1/2–1/3 или USF2 1/4")

    def connect(self):
        response = super().connect()
        self.patch_revision = response.patch_revision
        self.operations = response.supported_operations
        return response

    def send(self, message):
        with self.lock:
            if not self.ready:
                raise BridgeUnavailable("Capability handshake required")
            if isinstance(message, EncryptedReply):
                if not self.operations & (1 << (Operation.ENCRYPTED_REPLY - 1)):
                    raise BridgeUnavailable('Server channels require the ENCRYPTED_REPLY capability (legacy revision 3)')
                return self._request(Operation.ENCRYPTED_REPLY, message)
            return self._request(Operation.REPLAY if isinstance(message, FreshReplay) else Operation.CONTROL, message)


class ServerSerialInterface(CaptureSerialInterface):
    """One serial owner for capture and local bridge commands; ordinary mesh TX stays blocked."""
    def __init__(self, device, **kwargs):
        self._responses = queue.Queue(maxsize=4)
        self._exchange_lock = threading.Lock()
        super().__init__(device, **kwargs)

    def _handleFromRadio(self, data):
        from google.protobuf.message import DecodeError
        try:
            projection = bridge_pb2.FromRadioBridge.FromString(data)
        except DecodeError:
            self.failed.set()
            return
        if projection.usb_sf:
            try:
                self._responses.put_nowait(projection.usb_sf)
            except queue.Full:
                self.failed.set()
            return
        super()._handleFromRadio(data)

    def send_admin_receipt(self, recipient, public_key, text):
        from meshtastic.protobuf import mesh_pb2
        from meshtastic.serial_interface import SerialInterface
        import secrets
        if not 0 < recipient < 0xffffffff or len(public_key) != 32 or not 1 <= len(text.encode()) <= 180:
            raise ValueError('Invalid private receipt')
        message = mesh_pb2.ToRadio()
        p = message.packet
        p.to = recipient
        p.id = secrets.randbelow(0xffffffff) + 1
        p.pki_encrypted = True
        p.public_key = public_key
        p.decoded.portnum = 1
        p.decoded.payload = text.encode()
        p.want_ack = False
        # Only this bounded, authorized receipt path can bypass capture's TX block.
        SerialInterface._sendToRadioImpl(self, message)

    exchange = BridgeSerialInterface.exchange


@dataclass(frozen=True)
class EncryptedReply:
    sender: int
    requester: int
    outer_id: int
    channel_hash: int
    lora_context: bytes
    ciphertext: bytes

    def encode(self, session, token):
        for name in ('sender','requester','outer_id'):
            uint32(getattr(self,name),name,nonzero=True)
        if self.sender == 0xffffffff or self.requester == 0xffffffff or not 0 <= self.channel_hash <= 255 or len(self.lora_context)!=16 or not 1<=len(self.ciphertext)<=208:
            raise ValueError('Invalid encrypted reply')
        return header(Operation.ENCRYPTED_REPLY,session,token)+struct.pack('<IIII',self.sender,self.requester,self.outer_id,self.channel_hash)+self.lora_context+self.ciphertext


def encrypted_history_reply(item, entry, sender, requester, outer_id, lora):
    from meshtastic.protobuf import mesh_pb2
    from ..domain.channel_crypto import crypt_payload, channel_hash
    if isinstance(item,dict):
        if len(item['payload'])>160:
            raise ValueError('Server-channel history text exceeds radio budget')
        sf=storeforward_pb2.StoreAndForward(rr=9,text=item['payload'])
        from google.protobuf.internal.encoder import _VarintBytes
        payload=sf.SerializeToString()+b'\x30'+_VarintBytes(item['packet_id'])
        data=mesh_pb2.Data(portnum=65,payload=payload,reply_id=item['reply_id'],emoji=int(item['emoji']))
    else:
        data=mesh_pb2.Data(portnum=65,payload=item.SerializeToString())
    ciphertext=crypt_payload(entry['key'],sender,outer_id,data.SerializeToString())
    return EncryptedReply(sender,requester,outer_id,channel_hash(entry['name'],entry['key']),hashlib.sha256(lora).digest()[:16],ciphertext)
