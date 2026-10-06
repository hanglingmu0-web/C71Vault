"""Stage-1 C71 MIDI SysEx test protocol; no backup export or key operations."""
import hashlib
import struct
import zlib

MAX_PAYLOAD = 512
UART_BAUD = 31250
USB_SERIAL_BAUD = 115200

def sysex(raw):
    out = bytearray(b'\xf0\x7dC71')
    for p in range(0, len(raw), 7):
        group = raw[p:p+7]
        out.append(sum((b >> 7) << i for i, b in enumerate(group)))
        out.extend(b & 127 for b in group)
    out.append(0xf7)
    return bytes(out)

def frame(kind, session, sequence, payload=b''):
    if len(session) != 16 or not any(session) or not 1 <= kind <= 5 or len(payload) > MAX_PAYLOAD:
        raise ValueError('frame field')
    raw = struct.pack('>4sBB16sIH', b'C7IS', 1, kind, session, sequence, len(payload)) + payload
    return sysex(raw + struct.pack('>I', zlib.crc32(raw)))

def frames(data, session, chunk=128):
    if not 1 <= chunk <= MAX_PAYLOAD:
        raise ValueError('chunk')
    yield frame(1, session, 0)
    yield frame(2, session, 0, struct.pack('>Q', len(data)) + hashlib.sha256(data).digest())
    count = 0
    for count, p in enumerate(range(0, len(data), chunk), 1):
        yield frame(3, session, count, data[p:p+chunk])
    yield frame(4, session, count+1)

def pattern(size, seed):
    """Reproducible pseudo-random fixture; deliberately not cryptographic randomness."""
    result = bytearray()
    x = seed
    for _ in range(size):
        x ^= (x << 13) & 0xffffffff
        x ^= x >> 17
        x ^= (x << 5) & 0xffffffff
        result.append(x & 255)
    return bytes(result)

FIXTURES = [('text', b'C71VAULT MIDI TEST'), ('1KiB', pattern(1024, 0x12345678)), ('64KiB', pattern(65536, 0x9abcdef1))]

def backup_frames(data, client, session, series=bytes(16), chunk=512, label=None):
    """Authenticated START + ciphertext DATA; no commands or remote path fields."""
    import json,re
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    if not 64 <= len(data) <= 16*1024*1024 or not data.startswith(b'C71VAULT1\n'):
        raise ValueError('archive size/magic')
    header_length = struct.unpack('>I', data[10:14])[0]
    if not 2 <= header_length <= 1024 or 14+header_length > len(data):
        raise ValueError('archive header')
    key = json.loads(data[14:14+header_length])['key_id']
    if not isinstance(key,str) or not re.fullmatch('[0-9a-f]{16}',key) or len(series)!=16 or not 1<=chunk<=512:
        raise ValueError('metadata')
    body = b'\x01'+struct.pack('>Q',len(data))+hashlib.sha256(data).digest()+bytes.fromhex(client.client_id)+key.encode('ascii')+series
    if label is not None:
        encoded=label.encode('utf-8')
        if not label or len(label.encode('utf-16-le'))//2>100 or len(encoded)>300 or any(ord(c)<32 for c in label):raise ValueError('backup label')
        body=b'\x02'+body[1:]+struct.pack('>H',len(encoded))+encoded
    signature = client.private.sign(b'C71-MIDI-START1'+session+body,ec.ECDSA(hashes.SHA256()))
    yield frame(1,session,0)
    yield frame(2,session,0,body+bytes([len(signature)])+signature)
    count=0
    for count,p in enumerate(range(0,len(data),chunk),1):
        yield frame(3,session,count,data[p:p+chunk])
    yield frame(4,session,count+1)
