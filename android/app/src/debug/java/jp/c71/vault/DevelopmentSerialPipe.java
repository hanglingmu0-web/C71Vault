package jp.c71.vault;

import android.net.LocalServerSocket;
import android.net.LocalSocket;
import java.io.*;
import java.nio.charset.StandardCharsets;

/** Debug source set only. Never packaged in the release APK. */
public final class DevelopmentSerialPipe implements IsolatedSerialActivity.DebugPipe {
    final LocalServerSocket server;volatile LocalSocket peer;volatile boolean closed;
    public DevelopmentSerialPipe()throws IOException{server=new LocalServerSocket("c71vault-isolated-dev");}
    public InputStream open()throws IOException{peer=server.accept();if(closed){peer.close();throw new IOException("closed");}return peer.getInputStream();}
    public void status(String json)throws IOException{if(peer!=null){peer.getOutputStream().write((json+"\n").getBytes(StandardCharsets.UTF_8));peer.getOutputStream().flush();}}
    public void close()throws IOException{closed=true;try{if(peer!=null)peer.close();}finally{server.close();}}
}
