import base64,hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
from vault_crypto import pack,restore,selection_entries
from midi_transfer import ReceiptParser,verify_receipt
from midi_protocol import sysex

def test_multiple_files_and_folder_roundtrip(tmp_path):
    doc=tmp_path/'書類.docx';doc.write_bytes(b'PK test document')
    image=tmp_path/'写真.png';image.write_bytes(bytes(range(256)))
    folder=tmp_path/'資料';folder.mkdir();(folder/'本文.txt').write_text('日本語',encoding='utf8');(folder/'空').mkdir()
    archive=tmp_path/'out.c71b';key=bytes(range(32))
    meta=pack([doc,image,folder],archive,key)
    assert meta['file_count']==3
    restore(archive,tmp_path/'restored',key)
    for p in [doc,image,folder/'本文.txt']:assert (tmp_path/'restored'/p.relative_to(tmp_path)).read_bytes()==p.read_bytes()
    assert (tmp_path/'restored/資料/空').is_dir()

def test_duplicate_basename_rejected_without_archive(tmp_path):
    (tmp_path/'a').mkdir();(tmp_path/'b').mkdir()
    a=tmp_path/'a/test.txt';b=tmp_path/'b/test.txt';a.touch();b.touch()
    with pytest.raises(ValueError,match='重複'):pack([a,b],tmp_path/'out.c71b',bytes(32))
    assert not (tmp_path/'out.c71b').exists()

def test_parent_and_child_deduplicated(tmp_path):
    f=tmp_path/'a.txt';f.touch()
    roots,entries,dirs=selection_entries([f,tmp_path,f])
    assert roots==[tmp_path] and len(entries)==1

def receipt(code='ack',kind=3,sequence=1,count=512,session='73'*16,sha='a'*64):
    key=ec.generate_private_key(ec.SECP256R1());client=SimpleNamespace(device_key=key.public_key(),device={'device':'test-device'})
    p=dict(protocol='C71-MIDI-ACK1',device='test-device',session=session,type=kind,sequence=sequence,bytes=count,code=code)
    if code=='committed':p['sha256']=sha
    raw=json.dumps(p).encode();env=json.dumps({'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(key.sign(raw,ec.ECDSA(hashes.SHA256()))).decode()}).encode()
    return client,env

def test_fragmented_signed_ack_and_commit():
    client,env=receipt('committed',4,3,900)
    wire=sysex(env).replace(b'\x7dC71',b'\x7dC7A',1);parser=ReceiptParser();results=[]
    for b in wire:results.extend(parser.feed(bytes([b,0xf8])))
    assert results==[env]
    assert verify_receipt(env,client,b's'*16,4,3,900,'a'*64)['code']=='committed'

@pytest.mark.parametrize('code',['ack','verified'])
def test_end_requires_commit(code):
    client,env=receipt(code,4,3,900)
    with pytest.raises(ValueError):verify_receipt(env,client,b's'*16,4,3,900,'a'*64)

def test_wrong_session_and_old_sequence_ignored():
    client,env=receipt()
    assert verify_receipt(env,client,b't'*16,3,1,512,'a'*64) is None
    assert verify_receipt(env,client,b's'*16,3,2,512,'a'*64) is None

def test_ack_tamper_and_hash_mismatch_rejected():
    client,env=receipt('committed',4,3,900)
    with pytest.raises(ValueError):verify_receipt(env,client,b's'*16,4,3,900,'b'*64)
    bad=json.loads(env);bad['payload']=base64.b64encode(b'{}').decode()
    with pytest.raises(Exception):verify_receipt(json.dumps(bad),client,b's'*16,4,3,900,'a'*64)

def test_parser_bounds_and_resynchronizes():
    client,env=receipt();wire=sysex(env).replace(b'\x7dC71',b'\x7dC7A',1)
    parser=ReceiptParser();assert parser.feed(b'\xf0'+b'a'*5000)==[]
    assert parser.feed(wire)==[env]

def test_sender_waits_for_verified_commit(tmp_path,monkeypatch):
    import midi_transfer as m
    from cryptography.hazmat.primitives import serialization
    from test_midi_protocol import raw
    device=ec.generate_private_key(ec.SECP256R1());pc=ec.generate_private_key(ec.SECP256R1())
    client=SimpleNamespace(private=pc,client_id=hashlib.sha256(pc.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)).hexdigest(),device_key=device.public_key(),device={'device':'fixture'},state=tmp_path)
    monkeypatch.setattr(m,'pinned_client',lambda state:client);monkeypatch.setattr(m.time,'sleep',lambda _:None)
    source=tmp_path/'source.txt';source.write_text('文書試験'*300,encoding='utf8');archive=tmp_path/'test.c71b';pack([source],archive,bytes(32))
    class Port:
        def __init__(self,*a,**k):self.pending=bytearray();self.response=b'';self.received=bytearray();self.types=[]
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def reset_input_buffer(self):pass
        def flush(self):pass
        def write(self,b):
            assert not self.response, 'sender did not wait for ACK'
            self.pending.extend(b)
            if self.pending[-1]==0xf7:
                f=raw(self.pending);self.pending.clear();kind=f[5];self.types.append(kind)
                if kind==3:self.received.extend(f[28:-4])
                p=dict(protocol='C71-MIDI-ACK1',device='fixture',session=f[6:22].hex(),type=kind,sequence=int.from_bytes(f[22:26],'big'),bytes=len(self.received),code='committed' if kind==4 else 'ack')
                if kind==4:p['sha256']=hashlib.sha256(self.received).hexdigest()
                payload=json.dumps(p).encode();env=json.dumps({'payload':base64.b64encode(payload).decode(),'signature':base64.b64encode(device.sign(payload,ec.ECDSA(hashes.SHA256()))).decode()}).encode()
                self.response=sysex(env).replace(b'\x7dC71',b'\x7dC7A',1)
            return len(b)
        def read(self,n):result=self.response[:n];self.response=self.response[n:];return result
    cancel=SimpleNamespace(is_set=lambda:False,wait=lambda _:False);port=Port()
    result=m.send(archive,'a'*32,'TEST',lambda _:None,cancel,serial_factory=lambda *a,**k:port,label='文書試験')
    assert result['code']=='committed' and bytes(port.received)==archive.read_bytes()
    assert len(list((tmp_path/'receipts').glob('*-midi.json')))==1
