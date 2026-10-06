import base64
import hashlib
import json
from pathlib import Path
import sys
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
from vault_client import Client
from vault_transport import FolderBridge
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import ec

def device(path):
    key=ec.generate_private_key(ec.SECP256R1());der=key.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    info={'version':1,'device':'test-device','fingerprint':hashlib.sha256(der).hexdigest(),'public_key':base64.b64encode(der).decode()}
    (path/'device.json').write_text(json.dumps(info),encoding='utf-8');return key,info

def test_identity_persists_with_dpapi(tmp_path):
    b=FolderBridge(tmp_path/'bridge');a=Client(b,tmp_path/'state');c=Client(b,tmp_path/'state');assert a.client_id==c.client_id
    assert a.pub not in (tmp_path/'state'/'pc-identity.dpapi').read_bytes()

def test_device_key_change_rejected(tmp_path):
    b=FolderBridge(tmp_path/'bridge');device(b.path);c=Client(b,tmp_path/'state');c.read_device();c.trust_device();device(b.path)
    with pytest.raises(ValueError):c.read_device()

def test_signed_receipt_and_modified_receipt(tmp_path):
    b=FolderBridge(tmp_path/'bridge');key,info=device(b.path);c=Client(b,tmp_path/'state');c.read_device();rid='1'*32
    payload={'request_id':rid,'device':'test-device','ok':True,'result':{'saved':True}}
    raw=json.dumps(payload).encode();sig=key.sign(raw,ec.ECDSA(hashes.SHA256()))
    env={'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(sig).decode()};p=b.path/('r-'+rid+'.json');p.write_text(json.dumps(env))
    assert c.wait(rid,1)=={'saved':True}
    raw=raw.replace(b'true',b'false');env['payload']=base64.b64encode(raw).decode();p.write_text(json.dumps(env))
    with pytest.raises(Exception):c.wait(rid,1)
