package jp.c71.vault;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.*;
import org.json.*;
import java.io.*;
import java.security.*;
import java.security.spec.ECGenParameterSpec;
import java.nio.charset.StandardCharsets;
import java.util.*;
import static org.junit.Assert.*;

public class OpticalTest {
    Vault vault;OpticalReceiver receiver;KeyPair pc;String client,id,keyId="fedcba9876543210";byte[] data;JSONObject start;
    @Before public void prepare()throws Exception{
        vault=Vault.get(InstrumentationRegistry.getInstrumentation().getTargetContext());
        KeyPairGenerator g=KeyPairGenerator.getInstance("EC");g.initialize(new ECGenParameterSpec("secp256r1"));pc=g.generateKeyPair();client=Util.hash(pc.getPublic().getEncoded());
        vault.clients.put(client,new JSONObject().put("public_key",Util.b64(pc.getPublic().getEncoded())).put("name","optical test"));
        // Fixture only: optical transport checks custody presence, never decrypts a key.
        File keys=new File(vault.base,"recovery-keys");keys.mkdirs();Util.atomicJson(new File(keys,keyId+".json"),new JSONObject().put("fixture",true));
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(bytes);out.write("C71VAULT1\n".getBytes(StandardCharsets.US_ASCII));
        byte[] h=new JSONObject().put("version",1).put("salt",Util.b64(new byte[16])).put("nonce",Util.b64(new byte[12])).put("key_id",keyId).toString().getBytes(StandardCharsets.UTF_8);
        out.writeInt(h.length);out.write(h);out.write(new byte[1025]);data=bytes.toByteArray();
        receiver=new OpticalReceiver(vault);id=UUID.randomUUID().toString().replace("-","");
        start=base("begin",0).put("bytes",data.length).put("sha256",Util.hash(data)).put("key_id",keyId).put("series","d".repeat(32)).put("label","光学試験");
    }
    JSONObject base(String op,int seq)throws Exception{return new JSONObject().put("v",1).put("client",client).put("session",receiver.session).put("transfer",id).put("seq",seq).put("op",op);}
    String frame(JSONObject p)throws Exception{byte[] raw=p.toString().getBytes(StandardCharsets.UTF_8);Signature s=Signature.getInstance("SHA256withECDSA");s.initSign(pc.getPrivate());s.update(raw);return "C71O1:"+new JSONObject().put("payload",Util.b64(raw)).put("signature",Util.b64(s.sign())).toString();}
    JSONObject response(String text)throws Exception{String[] parts=text.substring(6).split("\\.");byte[] raw=Util.un64(parts[0]);assertTrue(raw.length==46||raw.length==78);Signature s=Signature.getInstance("SHA256withECDSA");s.initVerify(vault.publicKey);s.update(raw);assertTrue(s.verify(Util.un64(parts[1])));DataInputStream in=new DataInputStream(new ByteArrayInputStream(raw));assertEquals(1,in.readByte());in.skipBytes(32);int seq=in.readInt();int code=in.readUnsignedByte();long bytes=in.readLong();return new JSONObject().put("seq",seq).put("code",OpticalReceiver.CODES[code]).put("bytes",bytes);}
    @After public void cleanup()throws Exception{receiver.close();}
    @Test public void framesCommitOnlyAfterEndAndDuplicateIsIdempotent()throws Exception{
        String first=frame(start),ack=receiver.accept(first);assertEquals(ack,receiver.accept(first));assertEquals("ack",response(ack).getString("code"));
        int seq=1;for(int offset=0;offset<data.length;offset+=OpticalReceiver.CHUNK){byte[] b=Arrays.copyOfRange(data,offset,Math.min(data.length,offset+OpticalReceiver.CHUNK));receiver.accept(frame(base("data",seq++).put("data",Util.b64(b))));}
        assertFalse(new File(vault.archives,id).exists());String end=frame(base("end",seq));String result=receiver.accept(end);
        assertEquals("stored",response(result).getString("code"));assertEquals(result,receiver.accept(end));assertEquals(Util.hash(data),Util.hash(new File(vault.archives,id+"/data.c71b")));
    }
    @Test public void missingAndReorderedDataCannotCommit()throws Exception{receiver.accept(frame(start));assertEquals("sequence",response(receiver.accept(frame(base("data",2).put("data",Util.b64(new byte[512]))))).getString("code"));assertEquals("hash_mismatch",response(receiver.accept(frame(base("end",1)))).getString("code"));assertFalse(new File(vault.archives,id).exists());}
    @Test public void noOpticalExportOrKeyRecovery()throws Exception{receiver.accept(frame(start));for(String op:new String[]{"export","recover_key","list","delete"})assertEquals("forbidden",response(receiver.accept(frame(base(op,1)))).getString("code"));}
    @Test public void wrongSessionAndTamperAreRejected()throws Exception{
        String ready=receiver.previousReply;assertEquals(ready,receiver.accept(frame(new JSONObject(start.toString()).put("session","0".repeat(32)))));
        String good=frame(start);JSONObject env=new JSONObject(good.substring(6));env.put("signature",Util.b64(new byte[70]));try{receiver.accept("C71O1:"+env);fail();}catch(Exception expected){}assertFalse(new File(vault.archives,id).exists());
    }
}
