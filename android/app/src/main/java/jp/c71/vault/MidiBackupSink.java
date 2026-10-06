package jp.c71.vault;

import android.os.StatFs;
import org.json.JSONObject;
import java.io.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;

/** Write-only adapter to the existing authenticated vault store. */
final class MidiBackupSink implements AutoCloseable {
    static final long MAX_BACKUP=16*1024*1024;
    static final byte[] DOMAIN="C71-MIDI-START1".getBytes(StandardCharsets.US_ASCII);
    final Vault vault;final long expected;final String hash;final JSONObject metadata;
    final File staging;FileOutputStream output;
    private MidiBackupSink(Vault vault,long expected,String hash,JSONObject metadata)throws Exception{
        this.vault=vault;this.expected=expected;this.hash=hash;this.metadata=metadata;
        File directory=new File(vault.base,"midi-staging");if(!directory.mkdirs()&&!directory.isDirectory())throw new IOException("staging unavailable");
        staging=File.createTempFile("midi-",".part",directory);
        try{output=new FileOutputStream(staging);}catch(Exception e){staging.delete();throw e;}
    }
    static MidiBackupSink open(Vault vault,SerialFrame frame)throws Exception{
        if(vault==null)throw new IOException("backup input unavailable");
        byte[] p=frame.payload;if(p.length<114||(p[0]!=1&&p[0]!=2))throw new IOException("backup START length/version");
        int signedLength=105;String label="MIDIバックアップ";
        if(p[0]==2){
            int length=((p[105]&255)<<8)|(p[106]&255);signedLength=107+length;
            if(length<1||length>300||signedLength>=p.length)throw new IOException("backup label length");
            label=StandardCharsets.UTF_8.newDecoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT).decode(ByteBuffer.wrap(p,107,length)).toString();
            if(label.length()>100||label.chars().anyMatch(c->c<32))throw new IOException("backup label");
        }
        int sigLen=p[signedLength]&255;if(sigLen<8||sigLen>72||p.length!=signedLength+1+sigLen)throw new IOException("backup signature length");
        ByteBuffer b=ByteBuffer.wrap(p).order(ByteOrder.BIG_ENDIAN);b.get();long size=b.getLong();byte[] h=new byte[32],clientBytes=new byte[32],keyBytes=new byte[16],seriesBytes=new byte[16];b.get(h);b.get(clientBytes);b.get(keyBytes);b.get(seriesBytes);
        String hash=Util.hex(h),client=Util.hex(clientBytes),key=new String(keyBytes,StandardCharsets.US_ASCII),series=Util.hex(seriesBytes);
        synchronized(vault){
            if(!vault.clients.has(client))throw new IOException("unregistered sender");
            Signature signature=Signature.getInstance("SHA256withECDSA");signature.initVerify(Vault.decodeKey(vault.clients.getJSONObject(client).getString("public_key")));
            signature.update(DOMAIN);signature.update(frame.session);signature.update(p,0,signedLength);
            if(!signature.verify(Arrays.copyOfRange(p,signedLength+1,p.length)))throw new IOException("START signature mismatch");
            if(size<64||size>MAX_BACKUP||size>vault.maxArchive)throw new IOException("backup size limit");
            if(!key.matches("[0-9a-f]{16}")||!vault.recovery().has(key))throw new IOException("recovery key custody required");
            if(Util.size(vault.archives)+size+65536>vault.quota)throw new IOException("capacity: vault quota");
            if(new StatFs(vault.base.getPath()).getAvailableBytes()-2*size<vault.reserve)throw new IOException("capacity: staging and commit reserve");
        }
        JSONObject q=new JSONObject().put("id",Util.hex(frame.session)).put("client",client).put("bytes",size).put("sha256",hash).put("key_id",key).put("series",series).put("label",label);
        return new MidiBackupSink(vault,size,hash,q);
    }
    void write(byte[] bytes)throws IOException{output.write(bytes);}
    void commit()throws Exception{
        output.getFD().sync();output.close();output=null;
        if(staging.length()!=expected||!Util.hash(staging).equals(hash))throw new IOException("staging readback mismatch");
        try(InputStream input=new FileInputStream(staging)){vault.store(metadata,input);}
        // Vault.store's duplicate-ID path returns the old receipt; verify those bytes too.
        if(!Util.hash(new File(vault.archives,metadata.getString("id")+"/data.c71b")).equals(hash))throw new IOException("committed readback mismatch");
    }
    @Override public void close(){try{if(output!=null)output.close();}catch(IOException ignored){}output=null;if(staging.exists())staging.delete();}
}
