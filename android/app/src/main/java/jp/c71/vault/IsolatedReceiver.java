package jp.c71.vault;

import java.io.*;
import java.nio.*;
import java.security.*;
import java.util.*;

/** MIDI receive state machine; diagnostic hashing or authenticated write-only vault sink. */
final class IsolatedReceiver implements SerialFrame.Listener,AutoCloseable {
    static final long MAX_TEST_BYTES=1024*1024;
    interface Observer {void changed(IsolatedReceiver state);}
    interface Reply {void send(SerialFrame frame,boolean ok);}
    Reply reply;
    final Observer observer;final SerialFrame.Parser parser;final Vault vault;
    MidiBackupSink sink;boolean backupMode,committed;
    long limit=MAX_TEST_BYTES,received,wireBytes,sequence,crcFrames,errors,expected,next=1;
    String state="待機",lastError="なし",sha256="",expectedHash="";
    boolean active,complete,closed;
    byte[] session,lastRaw,startRaw,helloSession;
    MessageDigest digest;
    IsolatedReceiver(Observer observer){this(observer,null);}
    IsolatedReceiver(Observer observer,Vault vault){this.observer=observer;this.vault=vault;parser=new SerialFrame.Parser(this);}
    synchronized void feed(byte[] b,int n){if(closed)return;wireBytes+=n;parser.feed(b,n);}
    public synchronized void frame(SerialFrame f){
        if(closed)return;crcFrames++;
        try{accept(f);}catch(Exception e){error(e.getMessage());if(reply!=null)reply.send(f,false);return;}observer.changed(this);
        if(reply!=null)reply.send(f,true);
    }
    void accept(SerialFrame f)throws Exception {
        if(f.type==SerialFrame.HELLO){
            if(f.sequence!=0||f.payload.length!=0||active)throw new IOException("HELLO state/length");
            helloSession=f.session;if(complete)startRaw=null;state="HELLO受信・CRC一致";return;
        }
        if(f.type==SerialFrame.START){
            if(startRaw!=null&&Arrays.equals(startRaw,f.raw())){state=complete?"受信成功・SHA-256一致（再送）":"START再送・CRC一致";return;}
            if(active||f.sequence!=0)throw new IOException("START state/length");
            if(helloSession==null||!Arrays.equals(helloSession,f.session))throw new IOException("HELLO/session required");
            backupMode=f.payload.length!=40;committed=false;
            if(backupMode){sink=MidiBackupSink.open(vault,f);expected=sink.expected;expectedHash=sink.hash;}
            else {ByteBuffer b=ByteBuffer.wrap(f.payload).order(ByteOrder.BIG_ENDIAN);long size=b.getLong();byte[] hash=new byte[32];b.get(hash);
                if(size<0||size>limit)throw new IOException("capacity: diagnostic limit exceeded");expected=size;expectedHash=hex(hash);}
            session=f.session;received=0;sequence=0;next=1;sha256="";
            digest=MessageDigest.getInstance("SHA-256");active=true;complete=false;startRaw=f.raw();lastRaw=null;lastError="なし";state=backupMode?"staging受信中・未保存":"受信中（診断用・保存しません）";return;
        }
        if(session==null||!Arrays.equals(session,f.session))throw new IOException("session mismatch");
        if(f.type==SerialFrame.ABORT){if(f.payload.length!=0)throw new IOException("ABORT length");invalidate();state="送信側が中止";return;}
        if(lastRaw!=null&&f.sequence==sequence){if(Arrays.equals(lastRaw,f.raw())){state=complete?"受信成功・SHA-256一致（再送）":"同一フレーム再送・CRC一致";return;}throw new IOException("conflicting duplicate");}
        if(!active||f.sequence!=next)throw new IOException("sequence: expected "+next+", got "+f.sequence);
        if(f.type==SerialFrame.DATA){
            if(f.payload.length==0||received+f.payload.length>expected)throw new IOException("DATA length");
            if(sink!=null)sink.write(f.payload);digest.update(f.payload);received+=f.payload.length;state="受信中・CRC一致";
        }else if(f.type==SerialFrame.END){
            if(f.payload.length!=0||received!=expected)throw new IOException("END size mismatch");
            sha256=hex(digest.digest());digest=null;if(!sha256.equals(expectedHash))throw new IOException("SHA-256 mismatch");
            if(sink!=null){sink.commit();sink.close();sink=null;committed=true;}
            active=false;complete=true;state=committed?"保存完了・読み戻しSHA-256一致・commit済み":"受信成功・CRC/SHA-256一致（診断用・未保存）";
        }else throw new IOException("unexpected type");
        sequence=f.sequence;next=f.sequence+1;lastRaw=f.raw();
    }
    static String hex(byte[] bytes){StringBuilder b=new StringBuilder();for(byte v:bytes)b.append(String.format(java.util.Locale.ROOT,"%02x",v&255));return b.toString();}
    void invalidate(){if(sink!=null)sink.close();sink=null;active=false;complete=false;committed=false;digest=null;startRaw=null;lastRaw=null;helloSession=null;}
    public synchronized void error(String why){errors++;lastError=why==null?"receive error":why;invalidate();state="検証エラー・未保存";observer.changed(this);}
    public synchronized void close(){if(closed)return;parser.disconnected();if(active)error("disconnected before END");closed=true;if(!complete)state="停止・未保存";observer.changed(this);}
}
