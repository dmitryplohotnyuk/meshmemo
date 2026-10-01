"""Meshtastic channel payload encryption, not an authenticated transport.

Firmware CryptoEngine::initNonce: uint64 packet ID LE, uint32 sender LE,
then a four-byte big-endian block counter initially zero. Packets are <=237B,
so standard AES-CTR never carries into the preceding nonce bytes.
"""
import base64
import functools
import operator
import struct
from urllib.parse import urlparse
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from google.protobuf.message import DecodeError
from meshtastic.protobuf import channel_pb2, apponly_pb2, mesh_pb2
from meshtastic.util import DEFAULT_KEY


def channel_hash(name: str, key: bytes) -> int:
    return functools.reduce(operator.xor, name.encode('utf-8') + key, 0)


def validate_key(name, key):
    if not isinstance(name,str) or not 1 <= len(name.encode('utf-8')) <= 11 or any(ord(c)<32 for c in name):
        raise ValueError('Channel name must contain 1..11 UTF-8 bytes')
    if len(key) not in (16,32) or (len(key)==16 and key[:-1]==DEFAULT_KEY[:-1]) or not any(key):
        raise ValueError('A private 16- or 32-byte channel key is required')
    return name, key


def parse_channel(name='', key='', link=''):
    try:
        if link:
            if name or key or len(link)>2048:
                raise ValueError()
            url=urlparse(link)
            if url.scheme!='https' or url.hostname!='meshtastic.org' or url.path.rstrip('/')!='/e':
                raise ValueError()
            raw=base64.b64decode(url.fragment + '=' * (-len(url.fragment)%4),altchars=b'-_',validate=True)
            settings=apponly_pb2.ChannelSet.FromString(raw)
            if len(settings.settings)!=1:
                raise ValueError('Import a link containing exactly one channel')
            name,key=settings.settings[0].name,bytes(settings.settings[0].psk)
        else:
            key=base64.b64decode(key,validate=True)
        return validate_key(name,key)
    except (ValueError,DecodeError,UnicodeError):
        raise ValueError('Invalid channel name, private key or single-channel link') from None


def channel_settings(name,key):
    return channel_pb2.ChannelSettings(name=name,psk=key).SerializeToString(deterministic=True)


def crypt_payload(key, sender, packet_id, payload):
    if len(key) not in (16,32) or not 0<sender<0xffffffff or not 0<packet_id<=0xffffffff or not 0<len(payload)<=237:
        raise ValueError('Invalid channel packet')
    cipher=Cipher(algorithms.AES(key),modes.CTR(struct.pack('<QI',packet_id,sender)+bytes(4))).encryptor()
    return cipher.update(payload)+cipher.finalize()


def decode_packet(packet, entries):
    """Return one unambiguous supported Data payload; hash alone is never identity."""
    matches=[]
    for entry in entries:
        if channel_hash(entry['name'],entry['key'])!=packet.channel:
            continue
        try:
            data=mesh_pb2.Data.FromString(crypt_payload(entry['key'],getattr(packet,'from'),packet.id,packet.encrypted))
            if data.portnum not in (1,65) or not data.payload or len(data.payload)>237:
                continue
            if data.portnum==1:
                data.payload.decode('utf-8',errors='strict')
            else:
                from meshtastic.protobuf import storeforward_pb2
                sf=storeforward_pb2.StoreAndForward.FromString(data.payload)
                if sf.rr not in (64,65,66,67,68,106):
                    continue
            matches.append((entry,data))
        except (ValueError,DecodeError,UnicodeError):
            continue
    return matches[0] if len(matches)==1 else None
