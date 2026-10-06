package jp.c71.vault;

import org.json.JSONObject;
import java.nio.charset.StandardCharsets;

/** Fixed status fields only: never returns stored files, keys, paths or history. */
final class MidiReceipt {
    static byte[] encode(Vault vault,SerialFrame frame,IsolatedReceiver receiver,boolean ok)throws Exception {
        String code=!ok?"error":frame.type==SerialFrame.END?(receiver.committed?"committed":"verified"):"ack";
        long count=frame.type==SerialFrame.HELLO?0:receiver.received;
        JSONObject p=new JSONObject().put("protocol","C71-MIDI-ACK1").put("device",vault.device)
            .put("session",Util.hex(frame.session)).put("type",frame.type).put("sequence",frame.sequence)
            .put("code",code).put("bytes",count);
        if(code.equals("committed"))p.put("sha256",receiver.sha256);
        byte[] wire=SerialFrame.sysex(vault.envelope(p).toString().getBytes(StandardCharsets.UTF_8));
        wire[4]='A';return wire;
    }
}
