"""Stop-and-wait SysEx upload. Only signed COMMITTED is a successful backup."""
import base64,hashlib,json,struct,time,uuid
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from midi_protocol import backup_frames
from vault_optical import pinned_client

class ReceiptParser:
    def __init__(self):self.buffer=None
    def feed(self,data):
        replies=[]
        for b in data:
            if b>=0xf8:continue
            if b==0xf0:self.buffer=bytearray();continue
            if self.buffer is None:continue
            if b==0xf7:
                wire=bytes(self.buffer);self.buffer=None
                if not wire.startswith(b'\x7dC7A'):continue
                coded=wire[4:];raw=bytearray()
                for p in range(0,len(coded),8):
                    group=coded[p:p+8]
                    if len(group)<2 or group[0]>>(len(group)-1):break
                    raw.extend(v|(((group[0]>>i)&1)<<7) for i,v in enumerate(group[1:]))
                else:replies.append(bytes(raw))
            elif b>=128 or len(self.buffer)>=4096:self.buffer=None
            else:self.buffer.append(b)
        return replies

def verify_receipt(raw,client,session,kind,sequence,expected_bytes,expected_hash):
    env=json.loads(raw);payload=base64.b64decode(env['payload'],validate=True)
    client.device_key.verify(base64.b64decode(env['signature'],validate=True),payload,ec.ECDSA(hashes.SHA256()))
    p=json.loads(payload)
    if p.get('protocol')!='C71-MIDI-ACK1' or p.get('device')!=client.device['device']:raise ValueError('MIDI ACKの端末・形式が一致しません')
    if (p.get('session'),p.get('type'),p.get('sequence'))!=(session.hex(),kind,sequence):return None
    if p.get('code')=='error':raise RuntimeError('C71が転送を拒否しました。C71のエラー表示を確認してください')
    if type(p.get('bytes')) is not int or p['bytes']!=expected_bytes:raise ValueError('MIDI ACKの受信量が一致しません')
    if kind==4:
        if p.get('code')!='committed' or p.get('sha256')!=expected_hash:raise ValueError('MIDIの保存完了を確認できません')
    elif p.get('code')!='ack':raise ValueError('MIDI ACKの状態が不正です')
    return p

def send(archive,series,port_name,progress,cancel,state=None,timeout=15,serial_factory=None,label=None):
    import serial
    if archive.stat().st_size>16*1024*1024:raise ValueError('MIDI転送は暗号化後16MiBまでです。USBを選んでください')
    client=pinned_client(state);data=archive.read_bytes()
    session=uuid.uuid4().bytes;sha=hashlib.sha256(data).hexdigest()
    packets=iter(backup_frames(data,client,session,bytes.fromhex(series),label=label))
    parser=ReceiptParser();factory=serial_factory or serial.Serial;received=0;last=None;last_raw=None
    with factory(port_name,115200,timeout=.1,write_timeout=5) as port:
        # R3 resets when its USB serial port opens.
        if cancel.wait(3):raise InterruptedError('中止しました')
        port.reset_input_buffer()
        for index,packet in enumerate(packets):
            kind=1 if index==0 else 2 if index==1 else 3
            # Decode bounded outbound frame header, independent of archive/chunk count.
            coded=packet[5:-1];raw=bytearray()
            for p in range(0,len(coded),8):
                group=coded[p:p+8];raw.extend(v|(((group[0]>>i)&1)<<7) for i,v in enumerate(group[1:]))
            kind=raw[5];seq=struct.unpack('>I',raw[22:26])[0]
            if kind==3:received+=struct.unpack('>H',raw[26:28])[0]
            progress(f'MIDI {received:,} / {len(data):,} bytes — フレーム {seq} / ACK待ち')
            accepted=None
            for attempt in range(3):
                for pos in range(0,len(packet),16):
                    if cancel.is_set():raise InterruptedError('中止しました。保存完了は確認していません')
                    block=packet[pos:pos+16]
                    if port.write(block)!=len(block):raise IOError('USBシリアル書込みが不完全です')
                    port.flush();time.sleep(.008)
                deadline=time.monotonic()+(max(timeout,60) if kind==4 else timeout)
                while time.monotonic()<deadline:
                    if cancel.is_set():raise InterruptedError('中止しました。保存完了は確認していません')
                    for response in parser.feed(port.read(256)):
                        candidate=verify_receipt(response,client,session,kind,seq,received,sha)
                        if candidate is not None:accepted=candidate;last_raw=response;break
                    if accepted is not None:break
                if accepted is not None:break
            if accepted is None:raise TimeoutError('署名付きMIDI ACKが届きません。保存成功とは扱いません')
            last=accepted
    if last is None or last['code']!='committed':raise ValueError('C71の保存完了応答がありません')
    receipts=client.state/'receipts';receipts.mkdir(exist_ok=True)
    (receipts/(session.hex()+'-midi.json')).write_bytes(last_raw)
    return last
