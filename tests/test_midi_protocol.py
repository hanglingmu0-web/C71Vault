import hashlib,json,struct,zlib,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from midi_protocol import frame,frames,backup_frames,FIXTURES

def raw(wire):
    assert wire[:5]==b'\xf0\x7dC71' and wire[-1:]==b'\xf7'
    assert all(x<128 for x in wire[1:-1])
    coded=wire[5:-1];result=bytearray()
    for i in range(0,len(coded),8):
        mask=coded[i]
        for bit,low in enumerate(coded[i+1:i+8]):result.append(low|(((mask>>bit)&1)<<7))
    assert zlib.crc32(result[:-4])==struct.unpack('>I',result[-4:])[0]
    assert len(result)==32+struct.unpack('>H',result[26:28])[0]
    return bytes(result)

@pytest.mark.parametrize('name,data',FIXTURES,ids=[name for name,_ in FIXTURES])
def test_midi_fixture_stream(name,data):
    packets=[raw(x) for x in frames(data,b'x'*16)]
    assert packets[0][5]==1 and packets[-1][5]==4
    assert packets[1][36:68]==hashlib.sha256(data).digest()
    assert b''.join(p[28:-4] for p in packets[2:-1])==data
    assert [struct.unpack('>I',p[22:26])[0] for p in packets[2:]]==list(range(1,len(packets)-1))

def test_signed_backup_start_binds_session_and_metadata():
    private=ec.generate_private_key(ec.SECP256R1())
    client=SimpleNamespace(private=private,client_id=hashlib.sha256(private.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest())
    header=json.dumps({'key_id':'a'*16}).encode();data=b'C71VAULT1\n'+struct.pack('>I',len(header))+header+bytes(range(256))
    packets=[raw(x) for x in backup_frames(data,client,b's'*16)]
    body=packets[1][28:-4];assert body[0]==1
    private.public_key().verify(body[106:],b'C71-MIDI-START1'+b's'*16+body[:105],ec.ECDSA(hashes.SHA256()))
    with pytest.raises(Exception):private.public_key().verify(body[106:],b'C71-MIDI-START1'+b't'*16+body[:105],ec.ECDSA(hashes.SHA256()))

def test_invalid_fields_rejected():
    for args in [(99,b'x'*16,0,b''),(1,bytes(16),0,b''),(3,b'x'*16,1,b'x'*513)]:
        with pytest.raises(ValueError):frame(*args)
    with pytest.raises(ValueError):list(backup_frames(b'bad',None,b'x'*16))
