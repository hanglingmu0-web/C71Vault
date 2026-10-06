package jp.c71.vault;

import java.io.*;
import java.security.PublicKey;
import java.util.UUID;
import org.json.*;

/** Strict one-way data receiver. Replies contain only a bounded ACK/status schema. */
final class OpticalReceiver implements AutoCloseable {
    static final int CHUNK=512;
    static final long MAX_BYTES=16L*1024*1024;
    static final String[] CODES={"ready","ack","stored","sequence","unregistered","key_missing","capacity","exists","invalid","forbidden","hash_mismatch"};
    final Vault vault;
    final String session=UUID.randomUUID().toString().replace("-","");
    final File temporary;
    JSONObject begin;
    long received;
    int sequence=-1;
    String previousHash="", previousReply, transfer="";
    boolean complete;
    OpticalReceiver(Vault v)throws Exception{
        vault=v;temporary=new File(v.base,".optical-"+session);
        previousReply=status("ready",-1);
    }
    String status(String code,int seq)throws Exception{
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(bytes);
        out.writeByte(1);out.write(hexBytes(session));out.write(transfer.isEmpty()?new byte[16]:hexBytes(transfer));
        out.writeInt(seq);out.writeByte(java.util.Arrays.asList(CODES).indexOf(code));out.writeLong(received);
        if(code.equals("stored"))out.write(hexBytes(begin.getString("sha256")));
        byte[] raw=bytes.toByteArray();java.security.Signature s=java.security.Signature.getInstance("SHA256withECDSA");s.initSign(vault.signing);s.update(raw);
        return "C71A1:"+Util.b64(raw)+"."+Util.b64(s.sign());
    }
    static byte[] hexBytes(String hex){byte[] b=new byte[hex.length()/2];for(int i=0;i<b.length;i++)b[i]=(byte)Integer.parseInt(hex.substring(i*2,i*2+2),16);return b;}
    String accept(String frame)throws Exception{
        if(frame==null||frame.length()>4096||!frame.startsWith("C71O1:"))return previousReply;
        JSONObject env=new JSONObject(frame.substring(6));
        JSONObject unverified=new JSONObject(new String(Util.un64(env.getString("payload")),java.nio.charset.StandardCharsets.UTF_8));
        String client=unverified.getString("client");PublicKey publicKey;
        synchronized(vault){if(!vault.clients.has(client))return status("unregistered",sequence);publicKey=Vault.decodeKey(vault.clients.getJSONObject(client).getString("public_key"));}
        JSONObject q=Vault.verify(env,publicKey);
        if(q.optInt("v")!=1||!session.equals(q.optString("session")))return previousReply;
        int seq=q.getInt("seq");String hash=Util.hash(frame.getBytes(java.nio.charset.StandardCharsets.UTF_8));
        if(seq==sequence&&hash.equals(previousHash))return previousReply;
        if(complete||seq!=sequence+1)return status("sequence",sequence);
        String operation=q.getString("op");
        if(begin==null){
            if(!operation.equals("begin")||seq!=0)return status("invalid",sequence);
            String id=Util.id(q.getString("transfer"));long size=q.getLong("bytes");
            if(size<64||size>MAX_BYTES||!q.getString("sha256").matches("[0-9a-f]{64}"))return status("invalid",sequence);
            if(!vault.recovery().has(q.getString("key_id")))return status("key_missing",sequence);
            if(new android.os.StatFs(vault.base.getPath()).getAvailableBytes()-2*size<vault.reserve)return status("capacity",sequence);
            if(Util.size(vault.archives)+size+65536>vault.quota)return status("capacity",sequence);
            if(new File(vault.archives,id).exists())return status("exists",sequence);
            Util.id(q.getString("series"));
            if(q.getString("label").length()>100)return status("invalid",sequence);
            begin=q;transfer=id;Util.durable(temporary,new byte[0]);
        }else{
            if(!transfer.equals(q.optString("transfer"))||!begin.getString("client").equals(client))return status("invalid",sequence);
            if(operation.equals("data")){
                byte[] bytes=Util.un64(q.getString("data"));long remaining=begin.getLong("bytes")-received;
                if(bytes.length!=Math.min(CHUNK,remaining)||bytes.length==0)return status("invalid",sequence);
                try(FileOutputStream out=new FileOutputStream(temporary,true)){out.write(bytes);out.getFD().sync();}
                received+=bytes.length;
            }else if(operation.equals("end")){
                if(received!=begin.getLong("bytes")||!Util.hash(temporary).equals(begin.getString("sha256")))return status("hash_mismatch",sequence);
                JSONObject store=new JSONObject(begin.toString()).put("id",transfer);
                try(InputStream in=new FileInputStream(temporary)){vault.store(store,in);}
                if(!temporary.delete())throw new IOException("光学一時ファイルを削除できません");
                complete=true;
            }else return status("forbidden",sequence); // No export, recovery, list or delete path.
        }
        sequence=seq;previousHash=hash;previousReply=status(complete?"stored":"ack",seq);return previousReply;
    }
    @Override public void close()throws IOException{if(temporary.exists()&&!temporary.delete())throw new IOException("光学一時ファイルを削除できません");}
}
