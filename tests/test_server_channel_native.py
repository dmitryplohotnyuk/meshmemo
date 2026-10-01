import os
import subprocess
from dataclasses import replace
from meshtastic_sf.transport.protocol import header,Operation,Response,Status
from meshtastic_sf.transport.replay import EncryptedReply
import pytest

@pytest.mark.parametrize('change,expected', [({},Status.OK),({'requester':0xffffffff},Status.INVALID),({'channel_hash':256},Status.INVALID),({'sender':0},Status.INVALID)])
def test_encrypted_usb_adapter_validation_and_exact_retry(change,expected):
    binary=os.environ.get('USF_BRIDGE_HARNESS')
    if not binary: pytest.skip('Set USF_BRIDGE_HARNESS')
    import struct
    values={'sender':123,'requester':456,'channel_hash':23,**change}
    request=header(Operation.ENCRYPTED_REPLY,123,2)+struct.pack('<IIII',values['sender'],values['requester'],789,values['channel_hash'])+bytes(16)+b'x'*208
    commands=[header(Operation.HELLO,123,1).hex(),request.hex(),request.hex(),'count']
    result=subprocess.run([binary,'--replay'],input='\n'.join(commands)+'\n',capture_output=True,text=True,check=True).stdout.splitlines()
    capability = Response.decode(bytes.fromhex(result[0]))
    assert capability.supports(Operation.ENCRYPTED_REPLY)
    assert (capability.protocol_version, capability.patch_revision) in ((1, 3), (2, 4))
    assert Response.decode(bytes.fromhex(result[1])).status==expected
    assert result[1]==result[2]
    assert int(result[3])==(1 if expected==Status.OK else 0)
