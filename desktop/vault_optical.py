"""PC->phone QR data, phone->PC signed ACK/status only. No optical export API."""
import base64
import hashlib
import json
from pathlib import Path
import re
import time
import uuid
import struct
from cryptography.hazmat.primitives import hashes,serialization
from cryptography.hazmat.primitives.asymmetric import ec
from vault_client import Client,default_state
from vault_crypto import digest

CHUNK=512
MAX_BYTES=16*1024**2
CODES={'ready','ack','stored','sequence','unregistered','key_missing','capacity','exists','invalid','forbidden','hash_mismatch'}
CODE_LIST=['ready','ack','stored','sequence','unregistered','key_missing','capacity','exists','invalid','forbidden','hash_mismatch']

def pinned_client(state=None):
    client=Client(None,state=state)
    path=client.state/'device.json'
    if not path.exists():raise ValueError('先にUSBでC71と初回登録し、復元鍵をC71に保管してください')
    info=json.loads(path.read_text(encoding='utf-8'));raw=base64.b64decode(info['public_key'],validate=True)
    if hashlib.sha256(raw).hexdigest()!=info['fingerprint']:raise ValueError('登録済み端末情報が不正です')
    key=serialization.load_der_public_key(raw)
    if not isinstance(key,ec.EllipticCurvePublicKey) or not isinstance(key.curve,ec.SECP256R1):raise ValueError('端末鍵が不正です')
    client.device=info;client.device_key=key;return client

def decode_status(text,client):
    if not text.startswith('C71A1:') or len(text)>4096:raise ValueError('光学ACKではありません')
    payload,signature=text[6:].split('.')
    raw=base64.b64decode(payload,validate=True)
    client.device_key.verify(base64.b64decode(signature,validate=True),raw,ec.ECDSA(hashes.SHA256()))
    if len(raw) not in (46,78):raise ValueError('ACKの固定長形式が不正です')
    version,session,transfer,seq,code,received=struct.unpack('>B16s16siBQ',raw[:46])
    if version!=1 or code>=len(CODE_LIST) or (len(raw)==78)!=(code==2):raise ValueError('ACKの状態形式が不正です')
    p={'v':1,'device':client.device['device'],'session':session.hex(),'transfer':'' if transfer==b'\0'*16 else transfer.hex(),'seq':seq,'code':CODE_LIST[code],'bytes':received}
    if code==2:p['sha256']=raw[46:].hex()
    if not re.fullmatch('[0-9a-f]{32}',p.get('session','')):raise ValueError('セッションIDが不正です')
    if p.get('transfer')!='' and not re.fullmatch('[0-9a-f]{32}',p.get('transfer','')):raise ValueError('転送IDが不正です')
    if type(p.get('seq')) is not int or p['seq'] < -1 or type(p.get('bytes')) is not int or not 0<=p['bytes']<=MAX_BYTES:
        raise ValueError('ACKの連番・容量が不正です')
    if p['code']=='stored' and not re.fullmatch('[0-9a-f]{64}',p.get('sha256','')):raise ValueError('保存ハッシュが不正です')
    return p

def frames(client,archive,meta,label,series,session,transfer):
    seq=0
    common={'v':1,'session':session,'transfer':transfer}
    yield seq,'C71O1:'+json.dumps(client.envelope(dict(common,op='begin',seq=seq,bytes=meta['bytes'],sha256=meta['sha256'],key_id=meta['key_id'],label=label,series=series)),separators=(',',':'))
    with open(archive,'rb') as f:
        for block in iter(lambda:f.read(CHUNK),b''):
            seq+=1
            yield seq,'C71O1:'+json.dumps(client.envelope(dict(common,op='data',seq=seq,data=base64.b64encode(block).decode())),separators=(',',':'))
    seq+=1
    yield seq,'C71O1:'+json.dumps(client.envelope(dict(common,op='end',seq=seq)),separators=(',',':'))

def send(archive,meta,label,series,show_frame,progress,cancel,camera_index=0,state=None,timeout=120,diagnostic=lambda x:None):
    import cv2
    import zxingcpp
    if meta['bytes']>MAX_BYTES:raise ValueError('光学転送の上限は16MiBです。大きなデータはUSBを使ってください')
    if digest(archive)!=meta['sha256']:raise ValueError('暗号化ファイルが変更されています')
    client=pinned_client(state);capture=cv2.VideoCapture(camera_index,cv2.CAP_DSHOW)
    if not capture.isOpened():capture.release();raise RuntimeError('PCカメラを開けません。カメラ番号・Windowsのカメラ許可を確認してください')
    capture.set(cv2.CAP_PROP_FRAME_WIDTH,1280);capture.set(cv2.CAP_PROP_FRAME_HEIGHT,720)
    counts={'frames':0,'detected':0,'valid':0};last_diagnostic=time.monotonic()
    def read_status():
        nonlocal last_diagnostic
        if cancel.is_set():raise InterruptedError('光学送信を中止しました。保存完了は確認していません')
        ok,image=capture.read()
        if not ok:return None
        counts['frames']+=1
        if time.monotonic()-last_diagnostic>2:
            diagnostic(dict(counts));last_diagnostic=time.monotonic()
        for result in zxingcpp.read_barcodes(image,formats=zxingcpp.BarcodeFormat.QRCode):
            counts['detected']+=1
            try:
                p=decode_status(result.text,client);counts['valid']+=1
                return p,result.text
            except Exception:continue
        return None
    try:
        progress('C71で光学受付を開き、C71のACKをPCカメラに向けてください')
        deadline=time.monotonic()+timeout;hello=None
        while time.monotonic()<deadline:
            status=read_status()
            if status and status[0]['code']=='ready' and status[0]['seq']==-1:hello=status[0];break
        if hello is None:raise TimeoutError('C71の署名付き準備完了QRを読めませんでした')
        session=hello['session'];transfer=uuid.uuid4().hex;last=None;last_text=None
        total=(meta['bytes']+CHUNK-1)//CHUNK+2
        for seq,frame in frames(client,archive,meta,label,series,session,transfer):
            show_frame(frame);progress(f'光学送信 {seq+1}/{total} フレーム — ACK待ち')
            deadline=time.monotonic()+timeout
            while time.monotonic()<deadline:
                status=read_status()
                if status is None:continue
                p,text=status
                if p['session']!=session:continue
                if p['code'] in {'unregistered','key_missing','capacity','exists','invalid','forbidden','hash_mismatch'}:
                    raise RuntimeError('C71が光学転送を拒否しました: '+p['code'])
                if p['transfer']!=transfer or p['seq']!=seq:continue
                if p['code'] not in {'ack','stored'}:continue
                expected=min(max(seq,0)*CHUNK,meta['bytes'])
                if p['bytes']!=expected:raise ValueError('ACKの受信量が一致しません')
                last=p;last_text=text;break
            else:raise TimeoutError('署名付きACKが届きません。QRは再読取りできるよう保持しました。未完了です')
        if last is None or last['code']!='stored' or last.get('sha256')!=meta['sha256'] or last['bytes']!=meta['bytes']:
            raise ValueError('C71の保存・読み戻し完了を確認できませんでした')
        receipts=client.state/'receipts';receipts.mkdir(exist_ok=True)
        (receipts/(transfer+'-optical.json')).write_text(json.dumps({'signed_ack':last_text,'device_fingerprint':client.device['fingerprint']}),encoding='utf-8')
        return last
    finally:capture.release()
