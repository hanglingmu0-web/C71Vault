import base64,json,os,sys,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
from test_client import device
from vault_history import load_history,remember_transfer,remember_listing


def envelope(key,p):
    raw=json.dumps(p).encode()
    return dict(payload=base64.b64encode(raw).decode(),signature=base64.b64encode(key.sign(raw,ec.ECDSA(hashes.SHA256()))).decode())


def commit(state,key,code='committed',name='a'*32,device_id='test-device'):
    p=dict(protocol='C71-MIDI-ACK1',device=device_id,session=name,type=4,sequence=25,bytes=11838,code=code,sha256='b'*64)
    path=state/'receipts'/(name+'-midi.json');path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(envelope(key,p)))
    return path


def test_old_midi_receipt_visible_without_usb_or_sidecar(tmp_path):
    key,_=device(tmp_path);commit(tmp_path,key)
    row,=load_history(tmp_path)
    assert row['id']=='a'*32 and row['bytes']==11838 and row['key_id']==''
    assert 'USB未照合' in row['history_source']


@pytest.mark.parametrize('fault',['tamper','foreign-key','foreign-device','not-committed'])
def test_unverified_receipts_never_become_history(tmp_path,fault):
    key,_=device(tmp_path)
    signing=ec.generate_private_key(ec.SECP256R1()) if fault=='foreign-key' else key
    path=commit(tmp_path,signing,code='ack' if fault=='not-committed' else 'committed',device_id='other' if fault=='foreign-device' else 'test-device')
    if fault=='tamper':
        env=json.loads(path.read_text());p=json.loads(base64.b64decode(env['payload']));p['bytes']=1
        env['payload']=base64.b64encode(json.dumps(p).encode()).decode();path.write_text(json.dumps(env))
    assert load_history(tmp_path)==[]


def test_details_cannot_override_signed_size_hash_or_prove_commit(tmp_path):
    key,_=device(tmp_path)
    meta=dict(bytes=11838,sha256='b'*64,key_id='c'*16)
    remember_transfer(tmp_path,'a'*32,meta,'文書')
    assert load_history(tmp_path)==[]
    commit(tmp_path,key)
    row,=load_history(tmp_path);assert row['label']=='文書' and row['key_id']=='c'*16
    remember_transfer(tmp_path,'a'*32,dict(meta,bytes=999),'changed')
    row,=load_history(tmp_path);assert row['bytes']==11838 and row['label']=='MIDIバックアップ'


def test_usb_snapshot_enriches_and_supersedes_receipts_including_deleted(tmp_path):
    key,_=device(tmp_path);commit(tmp_path,key)
    row=dict(id='a'*32,label='C71の保存名',bytes=11838,key_id='c'*16,stored_at=1234567890000)
    client=SimpleNamespace(state=tmp_path,last_receipt=envelope(key,dict(device='test-device',ok=True,op='list',result={'archives':[row]})))
    remember_listing(client)
    loaded,=load_history(tmp_path);assert loaded['label']=='C71の保存名' and loaded['stored_at']==row['stored_at']
    client.last_receipt=envelope(key,dict(device='test-device',ok=True,op='list',result={'archives':[]}))
    remember_listing(client)
    assert load_history(tmp_path)==[]
    newer=commit(tmp_path,key,name='d'*32);os.utime(newer,(time.time()+2,time.time()+2))
    loaded,=load_history(tmp_path);assert loaded['id']=='d'*32


def test_corrupt_snapshot_does_not_hide_valid_midi_receipt(tmp_path):
    key,_=device(tmp_path);commit(tmp_path,key)
    (tmp_path/'history-list.json').write_text('{broken')
    assert len(load_history(tmp_path))==1
