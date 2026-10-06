from __future__ import annotations
import base64
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
import time
import uuid
import win32crypt
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from vault_crypto import digest

def default_state(): return Path(os.environ['LOCALAPPDATA'])/'C71Vault'

class Client:
    def __init__(self,bridge,state=None,log=lambda x:None):
        self.bridge=bridge;self.state=Path(state) if state else default_state();self.state.mkdir(parents=True,exist_ok=True);self.log=log
        f=self.state/'pc-identity.dpapi'
        if f.exists():
            raw=win32crypt.CryptUnprotectData(f.read_bytes(),None,None,None,0)[1]
            self.private=serialization.load_der_private_key(raw,None)
        else:
            self.private=ec.generate_private_key(ec.SECP256R1());raw=self.private.private_bytes(serialization.Encoding.DER,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
            protected=win32crypt.CryptProtectData(raw,'C71Vault PC identity',None,None,None,0)
            with f.open('xb') as out:out.write(protected);out.flush();os.fsync(out.fileno())
        self.pub=self.private.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
        self.client_id=hashlib.sha256(self.pub).hexdigest();self.device=None;self.device_key=None
    def read_device(self):
        info=json.loads(self.bridge.read('device.json',max_bytes=16384))
        der=base64.b64decode(info['public_key'],validate=True);fp=hashlib.sha256(der).hexdigest()
        key=serialization.load_der_public_key(der)
        if not isinstance(key,ec.EllipticCurvePublicKey) or not isinstance(key.curve,ec.SECP256R1) or info['fingerprint']!=fp or info['version']!=1:raise ValueError('端末情報が不正です')
        pins=self.state/'device.json'
        if pins.exists():
            old=json.loads(pins.read_text(encoding='utf-8'))
            if old['fingerprint']!=fp or old['device']!=info['device']:raise ValueError('登録したC71と署名鍵が違います。接続を中止しました')
        self.device=info;self.device_key=key
        if 'recovery_public_key' in info:
            from vault_recovery import custody_public_key
            custody_public_key(info,key)
            if pins.exists():pins.write_text(json.dumps(info,indent=2),encoding='utf-8')
        return info,not pins.exists()
    def trust_device(self):
        if self.device is None:raise ValueError('端末情報がありません')
        p=self.state/'device.json'
        if not p.exists():p.write_text(json.dumps(self.device,indent=2),encoding='utf-8')
    def envelope(self,payload):
        p=dict(payload);p['client']=self.client_id
        raw=json.dumps(p,ensure_ascii=False,separators=(',',':')).encode('utf-8')
        sig=self.private.sign(raw,ec.ECDSA(hashes.SHA256()))
        return {'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(sig).decode()}
    def submit(self,payload):
        p=dict(payload);p.setdefault('request_id',uuid.uuid4().hex)
        outbox=self.state/'outgoing';outbox.mkdir(exist_ok=True)
        f=outbox/('q-'+p['request_id']+'.json')
        with f.open('x',encoding='utf-8') as out:json.dump(self.envelope(p),out,separators=(',',':'))
        self.bridge.send_request(f)
        return p['request_id']
    def wait(self,request_id,timeout=300):
        name='r-'+request_id+'.json';end=time.monotonic()+timeout
        while time.monotonic()<end:
            if getattr(self,'cancel',None) is not None and self.cancel.is_set():raise InterruptedError('中止しました。保存済みかどうかはC71で確認してください')
            if self.bridge.has(name):
                try:env=json.loads(self.bridge.read(name))
                except (json.JSONDecodeError,UnicodeDecodeError):time.sleep(.5);continue
                raw=base64.b64decode(env['payload'],validate=True)
                self.device_key.verify(base64.b64decode(env['signature'],validate=True),raw,ec.ECDSA(hashes.SHA256()))
                p=json.loads(raw)
                if p.get('request_id')!=request_id or p.get('device')!=self.device['device']:raise ValueError('保存応答のIDが一致しません')
                if not p.get('ok'):raise RuntimeError(p.get('result',{}).get('error','端末が保存を拒否しました'))
                self.last_receipt=env
                (self.state/'outgoing'/('q-'+request_id+'.json')).unlink(missing_ok=True)
                return p['result']
            time.sleep(.5)
        raise TimeoutError('C71の保存確認が届きません。未確認として終了します。端末の受付状態を確認してください')
    def ack(self,request_id):
        try:self.submit({'op':'ack','target':request_id})
        except Exception as e:self.log('受渡し用ファイルの片付けは保留: '+str(e))
    def request(self,p,timeout=300,cleanup=True):
        rid=self.submit(p);result=self.wait(rid,timeout)
        if cleanup:self.ack(rid)
        return result
    def pair(self,timeout=300):
        self.log('PC鍵: '+self.client_id)
        self.log('初回はC71画面で、このPC鍵を確認して「このPCを登録」を押してください')
        result=self.request({'op':'pair','public_key':base64.b64encode(self.pub).decode(),'name':platform.node()},timeout)
        if not result.get('paired'):raise ValueError('PC登録を確認できませんでした')
        return result
    def list(self):
        rows=self.request({'op':'list'})['archives']
        try:
            from vault_history import remember_listing
            remember_listing(self)
        except OSError as error:self.log('一覧は取得済みですがPCへの履歴保存に失敗しました: '+str(error))
        return rows
    def backup(self,archive,metadata,label='バックアップ',series=None):
        archive=Path(archive);id=uuid.uuid4().hex
        if archive.stat().st_size>8*1024**3:raise ValueError('1回の暗号化バックアップは8GiB以下にしてください')
        self.log('暗号化データをUSB転送しています')
        self.bridge.upload(archive,'b-'+id+'.c71b')
        q={k:metadata[k] for k in ('bytes','sha256','key_id')};q.update(op='store',id=id,label=label,request_id=id)
        if series is not None:q['series']=series
        self.log('C71での保存・読み戻し検証を待っています')
        result=self.request(q,timeout=3600)
        if result.get('id')!=id or result.get('client')!=self.client_id or any(result.get(k)!=q[k] for k in ('bytes','sha256','key_id')):raise ValueError('C71の保存結果が送信データと一致しません')
        # Preserve signed receipts locally for audit, independently of the transfer folder.
        receipt=self.state/'receipts';receipt.mkdir(exist_ok=True);(receipt/(id+'.json')).write_text(json.dumps(self.last_receipt,ensure_ascii=False,indent=2),encoding='utf-8')
        self.log('保存成功: C71側で全データの読み戻し照合を確認しました')
        return result
    def download(self,id,destination):
        rid=self.submit({'op':'export','id':id});meta=self.wait(rid,timeout=3600)
        self.bridge.download('x-'+rid+'.c71b',destination,max_bytes=8*1024**3,expected_bytes=meta['bytes'])
        if Path(destination).stat().st_size!=meta['bytes'] or digest(destination)!=meta['sha256']:
            Path(destination).unlink(missing_ok=True);raise ValueError('復元用データのUSB受信結果が一致しません')
        self.ack(rid);return meta
