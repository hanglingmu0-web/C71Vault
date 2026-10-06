"""Exercise transfer completion and restart through the real Tk event queue."""
import base64,hashlib,json,sys,time,subprocess
from pathlib import Path
import tkinter as tk
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
import transfer_ui
import midi_transfer
import vault_optical
from vault_crypto import create_key
from test_client import device
from test_history import envelope


@pytest.mark.parametrize('fail',[False,True])
def test_midi_completion_updates_tree_and_survives_restart(tmp_path,monkeypatch,fail):
    # Keep each Tk lifecycle test in its own process, as in the packaged app.
    result=subprocess.run([sys.executable,str(Path(__file__).resolve()),str(tmp_path),str(int(fail))],capture_output=True,text=True,timeout=30)
    assert result.returncode==0,result.stdout+result.stderr


def exercise(tmp_path,monkeypatch,fail):
    state=tmp_path/'state';state.mkdir();signer,_=device(state)
    monkeypatch.setattr(transfer_ui,'default_state',lambda:state)
    monkeypatch.setattr(transfer_ui.TransferApp,'scan_ports',lambda self:self.com.set('TEST'))
    monkeypatch.setattr(vault_optical,'pinned_client',lambda:None)
    errors=[];monkeypatch.setattr(transfer_ui.messagebox,'showerror',lambda *args:errors.append(args))
    def send(archive,series,port,progress,cancel,label=None):
        if fail:raise TimeoutError('No signed commit ACK')
        p=dict(protocol='C71-MIDI-ACK1',device='test-device',session='a'*32,type=4,sequence=3,
               bytes=archive.stat().st_size,sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),code='committed')
        (state/'receipts').mkdir()
        (state/'receipts'/('a'*32+'-midi.json')).write_text(json.dumps(envelope(signer,p)))
        return p
    monkeypatch.setattr(midi_transfer,'send',send)
    source=tmp_path/'source.txt';source.write_text('復元対象の文書',encoding='utf-8')
    keyfile=tmp_path/'test.c71key';create_key(keyfile)
    root=tk.Tk();root.withdraw();app=transfer_ui.TransferApp(root)
    try:
        app.add_sources([source]);app.key.set(str(keyfile));app.label.set('試験文書');app.transport.set('MIDI');app.com.set('TEST')
        app.start_transfer()
        deadline=time.monotonic()+10
        while app.busy and time.monotonic()<deadline:root.update();time.sleep(.01)
        root.update();assert not app.busy
        if fail:
            assert errors and app.tree.get_children()==()
        else:
            assert not errors and app.tree.get_children()==('a'*32,)
            values=app.tree.item('a'*32,'values')
            assert values[1]=='試験文書' and 'USB未照合' in values[4]
            assert 'USB接続' in app.state.get()
    finally:app.busy=False;app.close()
    root=tk.Tk();root.withdraw();app=transfer_ui.TransferApp(root)
    try:
        deadline=time.monotonic()+.3
        while time.monotonic()<deadline:root.update();time.sleep(.01)
        assert len(app.tree.get_children())==(0 if fail else 1)
    finally:app.close()


if __name__=='__main__':
    with pytest.MonkeyPatch.context() as patch:
        exercise(Path(sys.argv[1]),patch,bool(int(sys.argv[2])))
