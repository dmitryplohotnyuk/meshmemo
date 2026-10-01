import base64
import json
import re
import struct
from pathlib import Path
import pytest
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
from fastapi.testclient import TestClient
from meshtastic.protobuf import mesh_pb2,storeforward_pb2,apponly_pb2,channel_pb2
from meshtastic_sf.domain.channel_crypto import crypt_payload,channel_hash,parse_channel,decode_packet
from meshtastic_sf.services.ingestion import Ingestor
from meshtastic_sf.services.replay import ReplayService
from meshtastic_sf.services.channel_admin import ChannelAdmin
from meshtastic_sf.diagnostics.ios_probe import ProbeScenario
from meshtastic_sf.storage.repository import HistoryRepository
from meshtastic_sf.transport.replay import EncryptedReply,encrypted_history_reply,ReplayBridgeClient
from meshtastic_sf.transport.protocol import HEADER,CAPABILITIES,BASE_COMMIT,Operation,Status
from meshtastic_sf.transport.client import BridgeUnavailable
from meshtastic_sf.web.application import create_app
KEY=bytes(range(32))
NAME='Testing'

@pytest.fixture
def world(tmp_path):
    repo=HistoryRepository(tmp_path/'history.db')
    ingestor=Ingestor(repo); scenario=ProbeScenario(123)
    for f in scenario.configuration(7): ingestor.accept(f.SerializeToString(),1800000000)
    yield repo,ingestor,scenario
    repo.close()


def frame(text,sender=987,packet_id=500,key=KEY,name=NAME):
    # Independent ECB counter construction checks the firmware wire format.
    plain=mesh_pb2.Data(portnum=1,payload=text).SerializeToString()
    nonce=struct.pack('<QI',packet_id,sender)
    aes=Cipher(algorithms.AES(key),modes.ECB()).encryptor()
    stream=b''.join(aes.update(nonce+struct.pack('>I',i)) for i in range((len(plain)+15)//16))
    encrypted=bytes(x^y for x,y in zip(plain,stream))
    p=mesh_pb2.MeshPacket(to=0xffffffff,id=packet_id,channel=channel_hash(name,key),encrypted=encrypted)
    setattr(p,'from',sender)
    return mesh_pb2.FromRadio(packet=p)


def test_catalog_encrypted_at_rest_persistence_and_missing_master(world):
    repo,ingestor,_=world
    n=repo.catalog.save(NAME,KEY)
    assert repo.catalog.entries()[0]['key']==KEY
    assert 'key' not in repo.catalog.public()[0]
    path=repo.path
    repo.close()
    assert KEY not in path.read_bytes()
    other=HistoryRepository(path)
    assert other.catalog.entries()[0]['key']==KEY
    other.close()
    Path(str(path)+'.channels.key').unlink()
    with pytest.raises(FileNotFoundError): HistoryRepository(path)


def test_capture_unknown_channel_decode_filter_and_policy(world):
    repo,ingestor,_=world
    encrypted=frame('Привіт'.encode())
    assert ingestor.accept(encrypted.SerializeToString(),1800000001) is None
    n=repo.catalog.save(NAME,KEY)
    saved=ingestor.accept(encrypted.SerializeToString(),1800000002)
    assert saved and repo.summary()['messages']==1
    assert ingestor.last_frame.packet.channel==n+8
    for text in (b'/history 6',b'/history invalid',b'/channel add Testing SECRET'):
        assert ingestor.accept(frame(text,packet_id=501).SerializeToString(),1800000003) is None
    repo.catalog.policy(n,False,False)
    assert ingestor.accept(frame(b'paused',packet_id=502).SerializeToString(),1800000004) is None
    assert repo.summary()['messages']==1
    assert repo.catalog.public()[0]['last_seen']==1800000004


def test_catalog_survives_capture_reconnect_with_more_than_eight_channels(world):
    repo,_,scenario=world
    for number in range(12):
        repo.catalog.save(f'Extra{number}', bytes([number + 1])*32)
    ingestor=Ingestor(repo)
    for f in scenario.configuration(8):
        ingestor.accept(f.SerializeToString(),1800000000)
    assert ingestor.ready
    assert len(ingestor.virtual_channels)==12
    assert ingestor.accept(frame(b'reconnected',name='Extra11',key=bytes([12])*32).SerializeToString(),1800000001)


def test_wrong_master_key_fails_at_startup(world):
    from cryptography.fernet import Fernet, InvalidToken
    repo,_,_=world
    repo.catalog.save(NAME,KEY)
    path=repo.path
    repo.close()
    Path(str(path)+'.channels.key').write_bytes(Fernet.generate_key())
    with pytest.raises(InvalidToken):
        HistoryRepository(path)


def test_wrong_key_hash_collision_and_key_rotation(world):
    repo,ingestor,_=world
    n=repo.catalog.save(NAME,KEY)
    assert ingestor.accept(frame(b'original').SerializeToString(),1800000001)
    # Same XOR channel hash, same key and different name => both valid; reject ambiguity.
    collision='Tesitng'
    assert channel_hash(NAME,KEY)==channel_hash(collision,KEY)
    repo.catalog.save(collision,KEY)
    assert ingestor.accept(frame(b'ambiguous',packet_id=600).SerializeToString(),1800000002) is None
    with pytest.raises(ValueError):repo.catalog.save(NAME,KEY)
    repo.catalog.save(NAME,b'z'*32,channel_id=n)
    assert not decode_packet(frame(b'wrong').packet,[{'name':NAME,'key':b'z'*32}])


def test_single_channel_link_and_private_key_validation():
    settings=apponly_pb2.ChannelSet(settings=[channel_pb2.ChannelSettings(name=NAME,psk=KEY)])
    link='https://meshtastic.org/e/#'+base64.urlsafe_b64encode(settings.SerializeToString()).decode().rstrip('=')
    assert parse_channel(link=link)==(NAME,KEY)
    settings.settings.add(name='Extra',psk=KEY)
    with pytest.raises(ValueError): parse_channel(link='https://meshtastic.org/e/#'+base64.urlsafe_b64encode(settings.SerializeToString()).decode())
    for name,key in [('too-long-channel',KEY),('Test',b'x'),('Test',bytes(32))]:
        with pytest.raises(ValueError):parse_channel(name,base64.b64encode(key).decode())


def test_server_channel_reply_roundtrip_and_firmware_gate(world):
    repo,ingestor,_=world
    n=repo.catalog.save(NAME,KEY,replay=True)
    ingestor.accept(frame(b'archive').SerializeToString(),1800000000)
    item={'sender':987,'packet_id':500,'payload':b'archive','reply_id':0,'emoji':False}
    reply=encrypted_history_reply(item,repo.catalog.entries()[0],987,999,777,ingestor.lora)
    raw=reply.encode(1,2)
    assert len(raw)<=256 and raw[4]==5
    data=mesh_pb2.Data.FromString(crypt_payload(KEY,987,777,raw[48:]))
    assert data.portnum==65
    sf=storeforward_pb2.StoreAndForward.FromString(data.payload)
    assert sf.rr==9 and sf.text==b'archive' and b'\x30\xf4\x03' in data.payload
    def old_firmware(payload,timeout):
        magic,op,_,_,session,token=HEADER.unpack_from(payload)
        return HEADER.pack(magic,op|128,0,0,session,token)+CAPABILITIES.pack(192,1,2,12,0,BASE_COMMIT.encode())
    client=ReplayBridgeClient(old_firmware);client.connect()
    with pytest.raises(BridgeUnavailable): client.send(reply)


def test_virtual_history_uses_encrypted_commands_and_disable_cancels(world):
    repo,ingestor,_=world
    n=repo.catalog.save(NAME,KEY,replay=True)
    ingestor.accept(frame(b'archive').SerializeToString(),1800000000)
    ingestor.accept(frame(b'second',packet_id=501).SerializeToString(),1800000001)
    repo.update_settings({**repo.get_settings(),'replay_enabled':True,'replay_heartbeat_enabled':False})
    ingestor.accept(frame(b'/history 6',sender=999,packet_id=555).SerializeToString(),1800000005)
    service=ReplayService(repo,clock=lambda:100.,wall=lambda:1800000010)
    service.accept(ingestor.last_frame,ingestor)
    assert len(service.job.packets)==2
    class Radio:
        sent=[]
        def exchange(self,payload,timeout):
            self.sent.append(payload)
            magic,op,_,_,session,token=HEADER.unpack_from(payload)
            return HEADER.pack(magic,op|128,0,0,session,token)+CAPABILITIES.pack(192,1,3,12,0,BASE_COMMIT.encode())
    radio=Radio();service.tick(radio,ingestor)
    assert radio.sent[-1][4]==5
    sender,_,packet_id,_=struct.unpack_from('<IIII',radio.sent[-1],16)
    decoded=mesh_pb2.Data.FromString(crypt_payload(KEY,sender,packet_id,radio.sent[-1][48:]))
    response=storeforward_pb2.StoreAndForward.FromString(decoded.payload)
    assert response.rr==9 and response.text==b'archive'
    repo.catalog.policy(n,True,False)
    service.next_send=0;service.tick(radio,ingestor)
    assert service.job is None


def test_dm_authorization_default_off_and_persistent_replay_guard(world):
    repo,ingestor,scenario=world
    admin=ChannelAdmin(repo)
    key=b'p'*32
    p=mesh_pb2.MeshPacket(to=scenario.node,id=700,pki_encrypted=True,public_key=key,decoded=mesh_pb2.Data(portnum=1,payload=('/channel add '+NAME+' '+base64.b64encode(KEY).decode()).encode()))
    setattr(p,'from',999)
    f=mesh_pb2.FromRadio(packet=p)
    admin.accept(f,ingestor);assert not repo.catalog.public()
    repo.catalog.set_remote_policy(True,[base64.b64encode(key).decode()])
    for mutation in ('pki','key','mqtt','broadcast'):
        bad=mesh_pb2.FromRadio();bad.CopyFrom(f)
        if mutation=='pki':bad.packet.pki_encrypted=False
        if mutation=='key':bad.packet.public_key=b'q'*32
        if mutation=='mqtt':bad.packet.via_mqtt=True
        if mutation=='broadcast':bad.packet.to=0xffffffff
        admin.accept(bad,ingestor)
        assert not repo.catalog.public()
    assert ingestor.accept(f.SerializeToString(),1800000000) is None
    admin.accept(f,ingestor)
    assert len(repo.catalog.public())==1 and not repo.catalog.public()[0]['replay']
    assert base64.b64encode(KEY).decode() not in admin.replies[0][2]
    second=ChannelAdmin(repo);second.accept(f,ingestor)
    assert not second.replies
    assert repo.summary()['messages']==0


def test_catalog_api_auth_csrf_secrets_and_persistence(tmp_path):
    app=create_app(str(tmp_path/'archive.db'),admin_password='test-only-password')
    with TestClient(app,base_url='http://127.0.0.1') as client:
        assert client.get('/api/channel-catalog').status_code==401
        client.headers['Authorization']='Basic YWRtaW46dGVzdC1vbmx5LXBhc3N3b3Jk'
        token=re.search(r'name="csrf-token" content="([^"]+)"',client.get('/').text)[1]
        data={'name':NAME,'key':base64.b64encode(KEY).decode()}
        assert client.post('/api/channel-catalog',json=data).status_code==403
        client.headers['X-CSRF-Token']=token
        assert client.post('/api/channel-catalog',json=data).status_code==200
        assert data['key'] not in client.get('/api/channel-catalog').text
        malformed=client.post('/api/channel-catalog',json={**data,'secret-field':data['key']})
        assert malformed.status_code==422 and data['key'] not in malformed.text
        assert client.post('/api/channel-catalog',json=data).status_code==422
        channel_id=client.get('/api/channel-catalog').json()[0]['id']
        app.state.repository.catalog.seen(channel_id,1800000000)
        assert client.post('/api/channel-catalog',json={'channel_id':channel_id,'name':NAME,'capture':False,'replay':False}).status_code==200
        assert app.state.repository.catalog.entries()[0]['key']==KEY
        assert client.get('/api/channel-catalog').json()[0]['last_seen']==1800000000
        assert client.post('/api/channel-catalog',json={'channel_id':channel_id,'name':'Renamed'}).status_code==200
        assert app.state.repository.catalog.entries()[0]['key']==KEY
        assert client.get('/api/channel-catalog').json()[0]['last_seen'] is None
        assert client.post('/api/channel-catalog',json={'channel_id':98765,'name':NAME}).status_code==422
        assert client.post(f'/api/channel-catalog/{channel_id}/policy',json={'capture':False,'replay':False}).status_code==200
        assert client.get('/api/channel-admin').json()=={'enabled':False,'public_keys':[]}
        assert client.post('/api/channel-admin',json={'enabled':True,'public_keys':[]}).status_code==422
