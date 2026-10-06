import base64
import io
import json
import os
from pathlib import Path
import secrets
import struct
import sys
import zipfile
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
import vault_crypto as v
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes

def source(tmp_path):
    p=tmp_path/'source';p.mkdir();(p/'日本語').mkdir();(p/'empty-dir').mkdir()
    (p/'日本語'/'契約書.txt').write_text('請求金額 330円\n契約内容を確認。'*100,encoding='utf-8')
    (p/'binary.dat').write_bytes(os.urandom(2*1024**2+27));(p/'zero').write_bytes(b'')
    return p

def test_roundtrip_unicode_empty_binary_and_mtime(tmp_path):
    src=source(tmp_path);key=secrets.token_bytes(32);a=tmp_path/'a.c71b'
    meta=v.pack(src,a,key);assert meta['file_count']==3
    result=v.restore(a,tmp_path/'restored',key);assert result['files']==3
    for p in src.rglob('*'):
        q=tmp_path/'restored'/p.relative_to(src)
        if p.is_file():assert v.digest(p)==v.digest(q);assert p.stat().st_mtime_ns==q.stat().st_mtime_ns
        else:assert q.is_dir()

def test_randomized_encryption(tmp_path):
    src=source(tmp_path);key=secrets.token_bytes(32)
    a,b=tmp_path/'a',tmp_path/'b';v.pack(src,a,key);v.pack(src,b,key);assert a.read_bytes()!=b.read_bytes()

@pytest.mark.parametrize('mode',['wrong-key','tamper-body','tamper-tag','truncated'])
def test_authentication_failure_creates_no_restore(tmp_path,mode):
    src=source(tmp_path);key=secrets.token_bytes(32);a=tmp_path/'a';v.pack(src,a,key)
    data=bytearray(a.read_bytes())
    if mode=='wrong-key':key=secrets.token_bytes(32)
    elif mode=='tamper-body':data[len(data)//2]^=1
    elif mode=='tamper-tag':data[-1]^=1
    else:data=data[:-30]
    a.write_bytes(data)
    with pytest.raises((ValueError,InvalidTag)):v.restore(a,tmp_path/'restore',key)
    assert not (tmp_path/'restore').exists()
    assert not list(tmp_path.glob('.c71-restore-*'))

@pytest.mark.parametrize('path',['../escape','/absolute','C:/file','a\\b','NUL','a/CON.txt','a:stream','a.','a//b'])
def test_unsafe_names(path):
    with pytest.raises(ValueError):v.safe_name(path)

def test_existing_targets_are_untouched(tmp_path):
    src=source(tmp_path);key=secrets.token_bytes(32);a=tmp_path/'a';v.pack(src,a,key)
    with pytest.raises(FileExistsError):v.restore(a,src,key)
    partial=tmp_path/'b.partial';partial.write_bytes(b'preserve me')
    with pytest.raises(FileExistsError):v.pack(src,tmp_path/'b',key)
    assert partial.read_bytes()==b'preserve me'

def test_recovery_key_roundtrip_and_no_overwrite(tmp_path):
    p=tmp_path/'key';key=v.create_key(p);assert v.load_key(p)==key
    with pytest.raises(FileExistsError):v.create_key(p)
    assert v.load_key(p)==key

def test_source_changed_is_failure(tmp_path):
    src=tmp_path/'src';src.mkdir();p=src/'file';p.write_text('original')
    with pytest.raises(ValueError):v.pack(src,tmp_path/'a',secrets.token_bytes(32),lambda _:p.write_text('now different'))
    assert not (tmp_path/'a').exists();assert not (tmp_path/'a.partial').exists()

def test_empty_folder(tmp_path):
    src=tmp_path/'src';src.mkdir();key=secrets.token_bytes(32);a=tmp_path/'a'
    v.pack(src,a,key);assert v.restore(a,tmp_path/'restored',key)['files']==0

def test_unreadable_subfolder_does_not_report_success(tmp_path,monkeypatch):
    src=tmp_path/'src';src.mkdir()
    def denied_walk(path,*,followlinks,onerror):
        onerror(PermissionError('unreadable subfolder'))
        return iter(())
    monkeypatch.setattr(v.os,'walk',denied_walk)
    with pytest.raises(PermissionError):v.pack(src,tmp_path/'a',secrets.token_bytes(32))
    assert not (tmp_path/'a').exists();assert not (tmp_path/'a.partial').exists()

def test_authenticated_malicious_zip_path_is_rejected(tmp_path):
    key=secrets.token_bytes(32);salt=secrets.token_bytes(16);nonce=secrets.token_bytes(12)
    data=io.BytesIO()
    with zipfile.ZipFile(data,'w') as z:
        z.writestr('files/../escape',b'x');z.writestr('manifest.json',json.dumps({'version':1,'files':[{'path':'../escape','bytes':1,'sha256':'0'*64,'mtime_ns':0}]}))
    header=json.dumps({'version':1,'salt':base64.b64encode(salt).decode(),'nonce':base64.b64encode(nonce).decode(),'key_id':v.key_id(key)}).encode()
    aad=v.MAGIC+struct.pack('>I',len(header))+header
    enc=Cipher(algorithms.AES(v._derive(key,salt)),modes.GCM(nonce)).encryptor();enc.authenticate_additional_data(aad)
    ciphertext=enc.update(data.getvalue())+enc.finalize();a=tmp_path/'a';a.write_bytes(aad+ciphertext+enc.tag)
    with pytest.raises(ValueError):v.restore(a,tmp_path/'restored',key)
    assert not (tmp_path/'escape').exists()
