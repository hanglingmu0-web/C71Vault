"""Create/send MIDI SysEx for an encrypted archive. Sending is not a receipt."""
import argparse,hashlib,json,time,uuid
from pathlib import Path
from midi_protocol import backup_frames,USB_SERIAL_BAUD,UART_BAUD
from vault_client import Client

def main():
    p=argparse.ArgumentParser();p.add_argument('archive',type=Path)
    p.add_argument('--state',type=Path,help='Existing PC identity directory; must already be registered on C71')
    group=p.add_mutually_exclusive_group(required=True);group.add_argument('--output',type=Path,help='Write a .syx stream');group.add_argument('--port',help='PC USB serial port for Arduino A')
    p.add_argument('--series',default='0'*32);p.add_argument('--uart-baud',type=int,choices=(9600,31250,115200),default=UART_BAUD)
    args=p.parse_args()
    if args.archive.stat().st_size>16*1024*1024:raise ValueError('16 MiB limit')
    data=args.archive.read_bytes();client=Client(None,state=args.state);session=uuid.uuid4().bytes
    packets=list(backup_frames(data,client,session,bytes.fromhex(args.series)))
    if args.output:
        with args.output.open('xb') as out:
            for packet in packets:out.write(packet)
    else:
        import serial
        with serial.Serial(args.port,USB_SERIAL_BAUD,timeout=1,write_timeout=5) as port:
            time.sleep(3) # UNO R3 resets on serial open.
            for packet in packets:
                for pos in range(0,len(packet),16):
                    block=packet[pos:pos+16];written=port.write(block)
                    if written!=len(block):raise IOError('serial write incomplete')
                    port.flush();time.sleep(max(.008,len(block)*10/args.uart_baud*1.5))
    print(json.dumps({'id':session.hex(),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),
                      'status':'prepared' if args.output else 'sent_unconfirmed','committed':False},indent=2))
    print('C71の「保存完了・読み戻しSHA-256一致・commit済み」を確認してください。送信だけでは保存成功ではありません。')
if __name__=='__main__':main()
