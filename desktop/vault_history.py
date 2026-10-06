"""Offline display of signed commit receipts and the last signed USB listing."""
import base64
import hashlib
import json
import os
import re
import time
from pathlib import Path
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False)
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, path)


def remember_transfer(state, archive_id, metadata, label):
    # Display hints only. Commit identity, size and hash come from the signed ACK.
    if not re.fullmatch('[0-9a-f]{32}', archive_id):
        raise ValueError('保存IDが不正です')
    write_json(Path(state)/'history-details'/(archive_id+'.json'),
               dict(label=label, key_id=metadata['key_id'], bytes=metadata['bytes'], sha256=metadata['sha256']))


def remember_listing(client):
    write_json(client.state/'history-list.json',
               dict(checked_at=time.time()*1000, envelope=client.last_receipt))


def load_history(state, log=lambda _: None):
    state = Path(state)
    if not (state/'device.json').exists():
        return []
    info = json.loads((state/'device.json').read_text(encoding='utf-8'))
    der = base64.b64decode(info['public_key'], validate=True)
    if hashlib.sha256(der).hexdigest() != info['fingerprint']:
        raise ValueError('登録済み端末情報が不正です')
    key = serialization.load_der_public_key(der)
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise ValueError('端末鍵が不正です')

    def verify(env):
        payload = base64.b64decode(env['payload'], validate=True)
        key.verify(base64.b64decode(env['signature'], validate=True), payload, ec.ECDSA(hashes.SHA256()))
        result = json.loads(payload)
        if result.get('device') != info['device']:
            raise ValueError('保存記録の端末が一致しません')
        return result

    rows = {}
    cutoff = 0
    snapshot = state/'history-list.json'
    if snapshot.exists():
        try:
            saved = json.loads(snapshot.read_text(encoding='utf-8'))
            p = verify(saved['envelope'])
            if p.get('ok') is not True or p.get('op') != 'list':
                raise ValueError('保存一覧の応答形式が不正です')
            for a in p['result']['archives']:
                if not re.fullmatch('[0-9a-f]{32}', a['id']):
                    raise ValueError('保存IDが不正です')
                if not isinstance(a['label'],str) or not isinstance(a['key_id'],str) or type(a['bytes']) is not int or type(a['stored_at']) is not int:
                    raise ValueError('保存一覧の項目が不正です')
            rows = {a['id']: dict(a, history_source='USB照合時点の履歴') for a in p['result']['archives']}
            cutoff = saved['checked_at']
        except Exception as error:
            rows = {}; cutoff = 0
            log('USB履歴キャッシュを読み込めません: '+str(error))

    for path in (state/'receipts').glob('*-midi.json'):
        try:
            p = verify(json.loads(path.read_text(encoding='utf-8')))
            archive_id = p.get('session', '')
            if p.get('protocol') != 'C71-MIDI-ACK1' or p.get('type') != 4 or p.get('code') != 'committed':
                continue
            if not re.fullmatch('[0-9a-f]{32}', archive_id) or not re.fullmatch('[0-9a-f]{64}', p.get('sha256', '')):
                raise ValueError('MIDI保存記録の形式が不正です')
            if type(p.get('bytes')) is not int or not 0 < p['bytes'] <= 16*1024**2:
                raise ValueError('MIDI保存記録のサイズが不正です')
            when = path.stat().st_mtime*1000
            if archive_id in rows or when <= cutoff:
                continue  # A later USB listing supersedes older local receipts, including deleted versions.
            row = dict(id=archive_id, bytes=p['bytes'], sha256=p['sha256'], stored_at=when,
                       label='MIDIバックアップ', key_id='', history_source='MIDI保存完了記録・USB未照合')
            details = state/'history-details'/(archive_id+'.json')
            if details.exists():
                try:
                    extra = json.loads(details.read_text(encoding='utf-8'))
                    if extra.get('bytes') == p['bytes'] and extra.get('sha256') == p['sha256']:
                        row['label'] = str(extra.get('label', row['label']))[:100]
                        kid = extra.get('key_id', '')
                        if re.fullmatch('[0-9a-f]{16}', kid): row['key_id'] = kid
                except (OSError, ValueError, TypeError):
                    pass
            rows[archive_id] = row
        except Exception as error:
            log('MIDI保存記録を読み込めません: '+path.name+' / '+str(error))
    return sorted(rows.values(), key=lambda a: a['stored_at'])
