"""Relay a physical Arduino COM port to the debug-only Android SysEx receiver.

Run `adb forward tcp:18771 localabstract:c71vault-isolated-dev` first and start
the debug receiver on C71. This is PC/ADB mediation, NOT a USB Host/isolated test.
"""
import argparse,hashlib,json,socket,time
from pathlib import Path
import serial
from midi_protocol import FIXTURES,USB_SERIAL_BAUD

def main():
    p=argparse.ArgumentParser();p.add_argument('--port',required=True);p.add_argument('--board',required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--timeout',type=float,default=120)
    args=p.parse_args();expected={hashlib.sha256(b).hexdigest():(n,len(b)) for n,b in FIXTURES};found={};pending=b'';wire=0;start=time.monotonic()
    with socket.create_connection(('127.0.0.1',18771),timeout=3) as phone,serial.Serial(args.port,USB_SERIAL_BAUD,timeout=0.02) as board:
        phone.settimeout(0.002)
        while time.monotonic()-start<args.timeout and len(found)<len(expected):
            data=board.read(2048)
            if data:phone.sendall(data);wire+=len(data)
            try:
                received=phone.recv(65536)
                if not received:raise RuntimeError('C71 debug receiver disconnected')
                pending+=received
            except socket.timeout:pass
            while b'\n' in pending:
                line,pending=pending.split(b'\n',1);s=json.loads(line)
                if s['complete'] and s['sha256'] in expected:
                    name,size=expected[s['sha256']]
                    if s['bytes']!=size:raise RuntimeError('size mismatch')
                    if name not in found:found[name]=s;print(name, json.dumps(s),flush=True)
        if len(found)!=len(expected):raise RuntimeError(f'incomplete: {list(found)}')
    report={'board':args.board,'port':args.port,'transport':'Arduino USB serial -> Windows relay -> ADB -> C71 debug app',
            'format':'MIDI 1.0 SysEx, 7-bit packed; not USB MIDI class', 'physically_isolated':False,'usb_host_direct_test':False,
            'wire_bytes_relayed':wire,'elapsed_seconds':time.monotonic()-start,'fixtures':found,'all_expected_hashes_match':True}
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print('PASS',args.report,flush=True)
if __name__=='__main__':main()
