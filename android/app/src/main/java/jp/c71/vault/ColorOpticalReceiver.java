package jp.c71.vault;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.util.*;
import org.json.JSONObject;

/** Optical v2. A bounded eight-packet receive window; no reverse file operations. */
final class ColorOpticalReceiver implements AutoCloseable {
    static final int CHUNK=1024, WINDOW=8, HEADER=75, MAX_PACKET=HEADER+CHUNK+73;
    static final int BEGIN=0, DATA=1, POLL=2, END=3;
    final Vault vault;
    final String session=UUID.randomUUID().toString().replace("-", "");
    final File temporary;
    String transfer="", client="", previousReply, beginHash="";
    JSONObject begin;
    int base=1, count, mask, previousBase=-1, previousMask;
    long received, previousBytes;
    byte[][] blocks=new byte[WINDOW][];
    byte[][] previousHashes=new byte[WINDOW][];
    boolean complete;
    String lastPollHash="";

    ColorOpticalReceiver(Vault vault)throws Exception {
        this.vault=vault;
        temporary=new File(vault.base,".optical2-"+session);
        previousReply=status("ready",0,0,0,0);
    }
    String status(String code,int at,int token,int bitmap,long bytes)throws Exception {
        ByteArrayOutputStream buffer=new ByteArrayOutputStream();
        DataOutputStream out=new DataOutputStream(buffer);
        out.writeByte(2);out.write(OpticalReceiver.hexBytes(session));
        out.write(transfer.isEmpty()?new byte[16]:OpticalReceiver.hexBytes(transfer));
        out.writeInt(at);out.writeInt(token);out.writeByte(bitmap);
        out.writeByte(Arrays.asList(OpticalReceiver.CODES).indexOf(code));out.writeLong(bytes);
        if(code.equals("stored"))out.write(OpticalReceiver.hexBytes(begin.getString("sha256")));
        byte[] raw=buffer.toByteArray();Signature signer=Signature.getInstance("SHA256withECDSA");
        signer.initSign(vault.signing);signer.update(raw);
        return "C71A2:"+Util.b64(raw)+"."+Util.b64(signer.sign());
    }
    static byte[] read(DataInputStream in,int length)throws IOException {
        byte[] result=new byte[length];in.readFully(result);return result;
    }
    String error(String code,int seq)throws Exception {
        return status(code,Math.max(0,Math.min(seq,16385)),0,0,received);
    }
    String accept(byte[] packet)throws Exception {
        if(closed)throw new IOException("この光学セッションは終了しています");
        if(packet==null||packet.length<HEADER+1||packet.length>MAX_PACKET)return previousReply;
        DataInputStream in=new DataInputStream(new ByteArrayInputStream(packet));
        if(!Arrays.equals(read(in,4),new byte[]{'C','7','D','2'}))return previousReply;
        int op=in.readUnsignedByte();String target=Util.hex(read(in,16));
        String id=Util.hex(read(in,16)),pc=Util.hex(read(in,32));int seq=in.readInt(),length=in.readUnsignedShort();
        if(!session.equals(target)||length>CHUNK||seq<0||seq>16385||packet.length<HEADER+length+1)return previousReply;
        byte[] body=read(in,length);int sigLength=in.readUnsignedByte();
        if(sigLength<8||sigLength>72||in.available()!=sigLength)return previousReply;
        PublicKey key;
        synchronized(vault){
            if(!vault.clients.has(pc))return error("unregistered",seq);
            key=Vault.decodeKey(vault.clients.getJSONObject(pc).getString("public_key"));
        }
        Signature verifier=Signature.getInstance("SHA256withECDSA");verifier.initVerify(key);
        verifier.update(packet,0,HEADER+length);
        if(!verifier.verify(read(in,sigLength)))throw new IOException("PC署名が一致しません");
        if(begin!=null&&(!transfer.equals(id)||!client.equals(pc)))return previousReply;
        // Hash signed content, not the randomized ECDSA encoding, for idempotent retries.
        String contentHash=Util.hash(Arrays.copyOf(packet,HEADER+length));
        if(complete){
            if(op==END&&seq==count+1&&length==0)return previousReply;
            return previousReply;
        }
        if(op==BEGIN){
            if(begin!=null)return contentHash.equals(beginHash)?status("ack",0,0,0,0):error("invalid",seq);
            if(seq!=0||length<74)return error("invalid",seq);
            DataInputStream b=new DataInputStream(new ByteArrayInputStream(body));
            long size=b.readLong();String hash=Util.hex(read(b,32));
            String keyId=new String(read(b,16),StandardCharsets.US_ASCII),series=Util.hex(read(b,16));
            int labelLength=b.readUnsignedShort();
            if(labelLength!=b.available()||labelLength>400||size<64||size>OpticalReceiver.MAX_BYTES)return error("invalid",seq);
            byte[] labelBytes=read(b,labelLength);
            String label=StandardCharsets.UTF_8.newDecoder().decode(java.nio.ByteBuffer.wrap(labelBytes)).toString();
            if(label.length()>100||label.chars().anyMatch(c->c<32)||!keyId.matches("[0-9a-f]{16}"))return error("invalid",seq);
            if(!vault.recovery().has(keyId))return error("key_missing",seq);
            if(new android.os.StatFs(vault.base.getPath()).getAvailableBytes()-2*size<vault.reserve
                    ||Util.size(vault.archives)+size+65536>vault.quota)return error("capacity",seq);
            if(new File(vault.archives,id).exists())return error("exists",seq);
            JSONObject metadata=new JSONObject().put("id",id).put("client",pc).put("bytes",size)
                    .put("sha256",hash).put("key_id",keyId).put("series",series).put("label",label);
            Util.durable(temporary,new byte[0]);
            begin=metadata;transfer=id;client=pc;beginHash=contentHash;count=(int)((size+CHUNK-1)/CHUNK);
            previousReply=status("ack",0,0,0,0);return previousReply;
        }
        if(begin==null)return error("invalid",seq);
        if(op==DATA){
            if(seq>=previousBase&&seq<previousBase+WINDOW&&previousBase>0){
                byte[] expected=previousHashes[seq-previousBase];
                return expected!=null&&Arrays.equals(expected,MessageDigest.getInstance("SHA-256").digest(body))?previousReply:error("invalid",seq);
            }
            if(seq<base||seq>=base+WINDOW||seq>count)return error("sequence",seq);
            int expected=(int)Math.min(CHUNK,begin.getLong("bytes")-(long)(seq-1)*CHUNK);
            if(length!=expected||length==0)return error("invalid",seq);
            int index=seq-base;
            if(blocks[index]!=null&&!Arrays.equals(blocks[index],body))return error("invalid",seq);
            blocks[index]=body;mask|=1<<index;
            return previousReply; // No per-data-frame ACK rendering or signature work.
        }
        if(op==POLL){
            if(contentHash.equals(lastPollHash))return previousReply;
            if(length!=4)return error("invalid",seq);
            int token=new DataInputStream(new ByteArrayInputStream(body)).readInt();
            if(token==0)return error("invalid",seq);
            if(seq==previousBase){
                previousReply=status("ack",seq,token,previousMask,previousBytes);lastPollHash=contentHash;return previousReply;
            }
            if(seq!=base||base>count)return error("sequence",seq);
            int full=(1<<Math.min(WINDOW,count-base+1))-1;
            long bytes=received;for(byte[] block:blocks)if(block!=null)bytes+=block.length;
            int ackMask=mask;
            if(mask==full){
                try(FileOutputStream output=new FileOutputStream(temporary,true)){
                    for(byte[] block:blocks)if(block!=null)output.write(block);
                    output.getFD().sync();
                }catch(IOException failure){
                    // A partial batch must never be appended again. This session becomes unusable.
                    close();throw failure;
                }
                previousBase=base;previousMask=mask;previousBytes=bytes;
                for(int i=0;i<WINDOW;i++)previousHashes[i]=blocks[i]==null?null:MessageDigest.getInstance("SHA-256").digest(blocks[i]);
                received=bytes;base+=WINDOW;mask=0;blocks=new byte[WINDOW][];
            }
            previousReply=status("ack",seq,token,ackMask,bytes);lastPollHash=contentHash;return previousReply;
        }
        if(op==END){
            if(length!=0||seq!=count+1||received!=begin.getLong("bytes")||mask!=0)return error("sequence",seq);
            if(!Util.hash(temporary).equals(begin.getString("sha256")))return error("hash_mismatch",seq);
            try(InputStream data=new FileInputStream(temporary)){vault.store(begin,data);}
            complete=true;
            previousReply=status("stored",seq,0,0,received);
            if(temporary.exists())temporary.delete();
            return previousReply;
        }
        return error("forbidden",seq);
    }
    boolean closed;
    @Override public void close()throws IOException {
        closed=true;
        if(temporary.exists()&&!temporary.delete())throw new IOException("光学一時ファイルを削除できません");
    }
}
