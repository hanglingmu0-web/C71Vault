"""C71 optical v2: two binary QR planes, signed packets, eight-frame ACKs.

This is a project-specific format, not HCC2D or JAB Code. Both planes must
belong to the same packet. QR error correction is independent on each plane.
"""
from __future__ import annotations
import base64
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import secrets
import struct
import time
import uuid

import qrcode
from qrcode.util import QRData, MODE_8BIT_BYTE
from PIL import Image
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec

from vault_optical import pinned_client, MAX_BYTES, CODE_LIST
from vault_crypto import digest

CHUNK = 1024
WINDOW = 8
VERSION = 20
BEGIN, DATA, POLL, END = range(4)
HEADER = struct.Struct('>4sB16s16s32sIH')
ACK = struct.Struct('>B16s16sIIBBQ')
LAYER = struct.Struct('>4sBH16s')
MAX_PACKET = HEADER.size + CHUNK + 73
# Index: red-plane dark bit + 2 * blue-plane dark bit.
PALETTE = ((255, 255, 255), (0, 200, 220), (220, 0, 0), (0, 0, 0))


@dataclass(frozen=True)
class ColorFrame:
    packet: bytes


def packet(client, session, transfer, op, seq, body=b''):
    if op not in (BEGIN, DATA, POLL, END) or not 0 <= seq <= 0xffffffff or len(body) > CHUNK:
        raise ValueError('不正な4色フレームです')
    raw = HEADER.pack(b'C7D2', op, bytes.fromhex(session), bytes.fromhex(transfer),
                      bytes.fromhex(client.client_id), seq, len(body)) + body
    signature = client.private.sign(raw, ec.ECDSA(hashes.SHA256()))
    return raw + bytes([len(signature)]) + signature


def unpack_packet(data, public_key):
    if not HEADER.size + 1 <= len(data) <= MAX_PACKET:
        raise ValueError('packet length')
    magic, op, session, transfer, client, seq, size = HEADER.unpack_from(data)
    end = HEADER.size + size
    if magic != b'C7D2' or op not in (BEGIN, DATA, POLL, END) or size > CHUNK or end >= len(data):
        raise ValueError('packet header')
    if not 8 <= data[end] <= 72 or len(data) != end + 1 + data[end]:
        raise ValueError('signature length')
    public_key.verify(data[end+1:], data[:end], ec.ECDSA(hashes.SHA256()))
    return dict(op=op, session=session.hex(), transfer=transfer.hex(), client=client.hex(),
                seq=seq, body=data[HEADER.size:end])


def begin_body(meta, label, series):
    encoded = label.encode('utf-8')
    if len(label.encode('utf-16-be')) // 2 > 100 or any(ord(c) < 32 for c in label):
        raise ValueError('保存名は制御文字を含まない100文字以内にしてください')
    if not 64 <= meta['bytes'] <= MAX_BYTES:
        raise ValueError('光学転送は64 bytes〜16 MiBの暗号化ファイルに対応します')
    key_id = meta['key_id'].encode('ascii')
    if len(key_id) != 16 or any(c not in b'0123456789abcdef' for c in key_id):
        raise ValueError('復元鍵IDが不正です')
    sha, source = bytes.fromhex(meta['sha256']), bytes.fromhex(series)
    if len(sha) != 32 or len(source) != 16:
        raise ValueError('保存情報が不正です')
    return struct.pack('>Q32s16s16sH', meta['bytes'], sha, key_id, source, len(encoded)) + encoded


def layers(data):
    if not HEADER.size + 1 <= len(data) <= MAX_PACKET:
        raise ValueError('packet length')
    mid = (len(data) + 1) // 2
    identity = hashlib.sha256(data).digest()[:16]
    return tuple(LAYER.pack(b'C7L2', index, len(data), identity) + part
                 for index, part in enumerate((data[:mid], data[mid:])))


def join_layers(first, second):
    parts = {}
    identity = None
    for raw in (first, second):
        if len(raw) < LAYER.size:
            raise ValueError('short layer')
        magic, index, size, tag = LAYER.unpack_from(raw)
        if magic != b'C7L2' or index not in (0, 1) or index in parts or not HEADER.size + 1 <= size <= MAX_PACKET:
            raise ValueError('layer header')
        if identity is not None and identity != (size, tag):
            raise ValueError('mixed frames')
        identity = (size, tag)
        expected = (size + 1) // 2 if index == 0 else size // 2
        if len(raw) != LAYER.size + expected:
            raise ValueError('layer length')
        parts[index] = raw[LAYER.size:]
    data = parts[0] + parts[1]
    if hashlib.sha256(data).digest()[:16] != identity[1]:
        raise ValueError('layer hash')
    return data


@lru_cache(maxsize=24)
def color_matrix(data):
    encoded=layers(data)
    probe=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=1,border=4)
    probe.add_data(QRData(encoded[0],mode=MODE_8BIT_BYTE));probe.make(fit=True)
    version=probe.version
    if version>VERSION:raise ValueError('4色コードの容量を超えています')
    mask=probe.best_mask_pattern()
    planes = []
    for raw in encoded:
        qr = qrcode.QRCode(version=version, error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=1, border=4, mask_pattern=mask)
        qr.add_data(QRData(raw, mode=MODE_8BIT_BYTE))
        qr.make(fit=False)
        planes.append(qr.get_matrix())
    side = len(planes[0])
    image = Image.new('RGB', (side, side))
    image.putdata([PALETTE[int(planes[0][y][x]) + 2 * int(planes[1][y][x])]
                   for y in range(side) for x in range(side)])
    return image


def render_color(frame, width, height):
    image = color_matrix(frame.packet)
    scale = min(int(width), int(height)) // image.width
    if scale < 1:
        raise ValueError('4色コード全体を表示できるまでウィンドウを拡大してください')
    return image.resize((image.width * scale, image.height * scale), Image.Resampling.NEAREST)


def decode_color_image(image):
    """Reference decoder for tests. Android decodes R/B from NV21 camera frames."""
    import zxingcpp
    decoded = []
    for channel in (0, 2):
        result = zxingcpp.read_barcode(image.convert('RGB').getchannel(channel),
                                      formats=zxingcpp.BarcodeFormat.QRCode)
        if result is None:
            raise ValueError('color plane unreadable')
        decoded.append(result.bytes)
    return join_layers(*decoded)


def decode_status(text, client):
    if not text.startswith('C71A2:') or len(text) > 512:
        raise ValueError('4色方式のACKではありません')
    encoded, signature = text[6:].split('.')
    raw = base64.b64decode(encoded, validate=True)
    client.device_key.verify(base64.b64decode(signature, validate=True), raw, ec.ECDSA(hashes.SHA256()))
    if len(raw) not in (ACK.size, ACK.size + 32):
        raise ValueError('ACK length')
    version, session, transfer, base, token, mask, code, received = ACK.unpack_from(raw)
    if version != 2 or code >= len(CODE_LIST) or (code == 2) != (len(raw) == ACK.size + 32):
        raise ValueError('ACK schema')
    if received > MAX_BYTES or base > MAX_BYTES // CHUNK + 1:
        raise ValueError('ACK bounds')
    if code in (0, 2) and mask != 0:
        raise ValueError('ACK mask')
    p = dict(session=session.hex(), transfer=transfer.hex(), base=base, token=token,
             mask=mask, code=CODE_LIST[code], bytes=received)
    if code == 2:
        p['sha256'] = raw[ACK.size:].hex()
    return p


def transfer(client, archive, meta, label, series, session, show, read_status, cancel,
             progress=lambda _: None, dwell=1.0, timeout=120):
    """Bounded selective-repeat windows. show() must return after actual drawing."""
    if not 0.2 <= dwell <= 3:
        raise ValueError('表示時間は0.2〜3秒にしてください')
    if digest(archive) != meta['sha256']:
        raise ValueError('暗号化ファイルが変更されています')
    body = begin_body(meta, label, series)
    transfer_id = uuid.uuid4().hex
    def make(op, seq, body=b''):
        return ColorFrame(packet(client, session, transfer_id, op, seq, body))
    def check_cancel():
        if cancel.is_set():
            raise InterruptedError('4色転送を中止しました。保存完了は確認していません')
    def wait_ack(frame, base, token, deadline):
        show(frame)
        while time.monotonic() < deadline:
            check_cancel()
            status = read_status()
            if status is None or status['session'] != session:
                continue
            if status['transfer'] not in (transfer_id, '0' * 32):
                continue
            if status['code'] not in ('ready', 'ack', 'stored'):
                raise RuntimeError('C71が4色転送を拒否しました: ' + status['code'])
            if (status['transfer'], status['base'], status['token']) == (transfer_id, base, token):
                return status
        raise TimeoutError('4色方式の署名付きACKが届きません。保存完了は未確認です')
    first = wait_ack(make(BEGIN, 0, body), 0, 0, time.monotonic() + timeout)
    if first['code'] != 'ack' or first['mask'] or first['bytes']:
        raise ValueError('開始ACKが不正です')
    count = (meta['bytes'] + CHUNK - 1) // CHUNK
    with open(archive, 'rb') as source:
        for base in range(1, count + 1, WINDOW):
            blocks = [source.read(CHUNK) for _ in range(min(WINDOW, count - base + 1))]
            frames = [make(DATA, base+i, b) for i, b in enumerate(blocks)]
            full = (1 << len(frames)) - 1
            mask = 0
            deadline = time.monotonic() + timeout
            while mask != full:
                check_cancel()
                if time.monotonic() >= deadline:
                    raise TimeoutError('4色データの受信が進みません。表示時間と位置合わせを確認してください')
                for i, frame in enumerate(frames):
                    if not mask & (1 << i):
                        progress(f'4色送信 {base+i}/{count} — 1,024 bytes / 最大8枚まとめACK')
                        show(frame)
                        if cancel.wait(dwell):
                            check_cancel()
                token = secrets.randbelow(0xffffffff) + 1
                progress(f'4色転送：{base}〜{base+len(frames)-1}枚目の受信確認待ち')
                status = wait_ack(make(POLL, base, struct.pack('>I', token)), base, token, deadline)
                new_mask = status['mask']
                expected = (base-1)*CHUNK + sum(len(b) for i, b in enumerate(blocks) if new_mask & (1 << i))
                if status['code'] != 'ack' or new_mask & ~full or new_mask & mask != mask or status['bytes'] != expected:
                    raise ValueError('まとめACKの受信量・ビットマップが不正です')
                mask = new_mask
    final = wait_ack(make(END, count+1), count+1, 0, time.monotonic() + timeout)
    if final['code'] != 'stored' or final['bytes'] != meta['bytes'] or final.get('sha256') != meta['sha256']:
        raise ValueError('C71の保存・読み戻し照合を確認できませんでした')
    return final


def send(archive, meta, label, series, show_frame, progress, cancel, camera_index=0,
         state=None, timeout=120, dwell=1.0, diagnostic=lambda _: None):
    import cv2
    import zxingcpp
    client = pinned_client(state)
    begin_body(meta, label, series)
    capture = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
    if not capture.isOpened():
        capture.release()
        raise RuntimeError('PCカメラを開けません')
    capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
    last_signed = None
    counters={'frames':0,'detected':0,'valid':0}
    last_diagnostic=0
    def read_status():
        nonlocal last_signed,last_diagnostic
        ok, image = capture.read()
        if not ok:
            cancel.wait(0.02)
            return None
        counters['frames']+=1
        if time.monotonic()-last_diagnostic>3:
            diagnostic(dict(counters));last_diagnostic=time.monotonic()
        for result in zxingcpp.read_barcodes(image, formats=zxingcpp.BarcodeFormat.QRCode):
            counters['detected']+=1
            try:
                value = decode_status(result.text, client)
                counters['valid']+=1;counters.update(code=value['code'],base=value['base'],mask=value['mask'],bytes=value['bytes'])
                last_signed = result.text
                return value
            except Exception:
                continue
        return None
    try:
        progress('C71で「4色光学受付」を開き、白黒のACKをPCカメラへ向けてください')
        deadline = time.monotonic() + timeout
        ready = None
        while time.monotonic() < deadline and not cancel.is_set():
            p = read_status()
            if p and p['code'] == 'ready' and p['base'] == 0 and p['token'] == 0 and p['bytes'] == 0 and p['transfer'] == '0'*32:
                ready = p
                break
        if ready is None:
            raise TimeoutError('4色方式の準備完了ACKを確認できません')
        result = transfer(client, archive, meta, label, series, ready['session'], show_frame,
                          read_status, cancel, progress, dwell, timeout)
        receipts = client.state/'receipts'
        receipts.mkdir(exist_ok=True)
        (receipts/(result['transfer']+'-optical-v2.json')).write_text(json.dumps({
            'signed_ack': last_signed, 'device_fingerprint': client.device['fingerprint']
        }), encoding='utf-8')
        return result
    finally:
        capture.release()
