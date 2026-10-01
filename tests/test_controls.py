import queue
import threading
import time
from fastapi.testclient import TestClient
from functools import partial

from meshtastic_sf.services.runtime import ServerRuntime
from meshtastic_sf.storage.repository import HistoryRepository
from meshtastic_sf.transport.ports import select_port
from meshtastic_sf.web.application import create_app
create_app = partial(create_app, admin_password="test-only-password")
TestClient = partial(TestClient, headers={"Authorization": "Basic YWRtaW46dGVzdC1vbmx5LXBhc3N3b3Jk"})
from test_web import token
from test_replay import world, request, seed, enable, SF


def test_auto_selection_follows_identity_without_guessing():
    settings={'mode':'auto','port':'COM7','identity':'target'}
    ports=[{'device':'COM11','identity':'target','candidate':True},{'device':'COM9','identity':'other','candidate':True}]
    assert select_port(settings,ports)[0]=='COM11'
    assert select_port(settings,ports[1:])[0] is None
    assert select_port({**settings,'identity':''},ports)[0] is None
    assert select_port({**settings,'identity':''},ports[:1])[0]=='COM11'
    assert select_port({**settings,'mode':'off'},ports)[0] is None


def test_policy_controls_change_actual_reply_and_pacing(world):
    repo, ingestor, scenario, service, radio, timer=world
    seed(ingestor,scenario,10)
    policy={**repo.get_settings(),'replay_enabled':True,'replay_limit':2,'replay_window_minutes':10,
            'replay_max_window_minutes':30,'replay_interval_seconds':12,'replay_heartbeat_enabled':False}
    repo.update_settings(policy)
    service.accept(request(scenario),ingestor) # request asks 60 minutes, capped at 30
    service.tick(radio,ingestor)
    header=SF.FromString(radio.sent[-1][44:])
    assert header.history.history_messages==2 and header.history.window==30*60000
    timer[0]+=5;service.tick(radio,ingestor);assert len(radio.sent)==2
    timer[0]+=7;service.tick(radio,ingestor);assert len(radio.sent)==3
    timer[0]+=12;service.tick(radio,ingestor);assert service.job is None
    timer[0]+=1000;service.tick(radio,ingestor);assert len(radio.sent)==4 # no announcement


def test_connection_api_validation_reconnect_and_persistence(tmp_path):
    from meshtastic_sf.diagnostics.ios_probe import ProbeScenario
    opened=[]
    class FakeRadio:
        def __init__(self,device):
            opened.append(device);self.frames=queue.Queue();self.failed=threading.Event()
            for frame in ProbeScenario(123).configuration(7):
                self.frames.put((frame.SerializeToString(),int(time.time())))
        def next_frame(self):
            try:return self.frames.get(timeout=.01)
            except queue.Empty:return None
        def close(self):pass
    ports=[{'device':'TEST1','description':'Synthetic USB','identity':'stable-id','candidate':True}]
    def factory(repo,device):
        return ServerRuntime(repo,device,radio_factory=FakeRadio,port_provider=lambda:ports)
    app=create_app(str(tmp_path/'history.db'),runtime_factory=factory)
    with TestClient(app,base_url='http://127.0.0.1') as client:
        headers=token(client)
        assert client.get('/api/ports').json()==[{'device':'TEST1','description':'Synthetic USB','candidate':True}]
        assert client.post('/api/connection',json={'mode':'manual','port':'missing'},headers=headers).status_code==409
        assert client.post('/api/connection',json={'mode':'manual','port':'TEST1'}).status_code==403
        assert client.post('/api/connection',json={'mode':'manual','port':'TEST1'},headers=headers).status_code==200
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and app.state.repository.get_connection()['identity']!='stable-id':time.sleep(.02)
        assert opened==['TEST1']
        assert app.state.repository.get_connection()['identity']=='stable-id'
        ports[0]['device']='TEST2'
        assert client.post('/api/connection',json={'mode':'auto'},headers=headers).status_code==200
        deadline=time.monotonic()+3
        while time.monotonic()<deadline and opened!=['TEST1','TEST2']:time.sleep(.02)
        assert opened==['TEST1','TEST2']
        assert 'identity' not in client.get('/api/status').json()['connection']
        policy=client.get('/api/status').json()['settings']
        assert client.post('/api/settings',json={**policy,'replay_limit':101},headers=headers).status_code==422
        assert client.post('/api/settings',json={**policy,'replay_window_minutes':100,'replay_max_window_minutes':50},headers=headers).status_code==422
        assert client.post('/api/settings',json={**policy,'replay_limit':50,'replay_interval_seconds':10},headers=headers).status_code==200
        assert client.post('/api/connection',json={'mode':'off'},headers=headers).status_code==200
    reopened=HistoryRepository(tmp_path/'history.db')
    try:
        assert reopened.get_connection()['mode']=='off'
        assert reopened.get_connection()['identity']=='stable-id'
        assert reopened.get_settings()['replay_limit']==50
        # Restarting with CLI --device does not replace an explicit UI choice.
        factory(reopened,'TEST3')
        assert reopened.get_connection()['mode']=='off'
    finally:reopened.close()
