package jp.c71.vault;

import androidx.test.platform.app.InstrumentationRegistry;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import org.junit.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.ECGenParameterSpec;
import java.util.*;
import static org.junit.Assert.*;

public class ColorOpticalTest {
    Vault vault;ColorOpticalReceiver receiver;KeyPair pc;
    String client,id,keyId="c030c030c030c030";byte[] data;
    @Before public void prepare()throws Exception {
        vault=Vault.get(InstrumentationRegistry.getInstrumentation().getTargetContext());
        KeyPairGenerator g=KeyPairGenerator.getInstance("EC");g.initialize(new ECGenParameterSpec("secp256r1"));pc=g.generateKeyPair();client=Util.hash(pc.getPublic().getEncoded());
        vault.clients.put(client,new JSONObject().put("public_key",Util.b64(pc.getPublic().getEncoded())).put("name","color test"));
        File keys=new File(vault.base,"recovery-keys");keys.mkdirs();Util.atomicJson(new File(keys,keyId+".json"),new JSONObject().put("fixture",true));
        ByteArrayOutputStream b=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(b);
        out.write("C71VAULT1\n".getBytes(StandardCharsets.US_ASCII));
        byte[] h=new JSONObject().put("version",1).put("salt",Util.b64(new byte[16])).put("nonce",Util.b64(new byte[12])).put("key_id",keyId).toString().getBytes(StandardCharsets.UTF_8);
        out.writeInt(h.length);out.write(h);byte[] payload=new byte[9500];new Random(3).nextBytes(payload);out.write(payload);data=b.toByteArray();
        receiver=new ColorOpticalReceiver(vault);id=UUID.randomUUID().toString().replace("-","");
    }
    @After public void cleanup()throws Exception {
        receiver.close();if(new File(vault.archives,id).exists())vault.deleteLocal(id);
        vault.clients.remove(client);new File(vault.base,"recovery-keys/"+keyId+".json").delete();
    }
    byte[] frame(int op,int seq,byte[] body)throws Exception{return frame(op,seq,body,receiver.session,id);}
    byte[] frame(int op,int seq,byte[] body,String session,String transfer)throws Exception {
        ByteArrayOutputStream b=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(b);
        out.writeBytes("C7D2");out.writeByte(op);out.write(OpticalReceiver.hexBytes(session));out.write(OpticalReceiver.hexBytes(transfer));out.write(OpticalReceiver.hexBytes(client));out.writeInt(seq);out.writeShort(body.length);out.write(body);
        byte[] raw=b.toByteArray();Signature sig=Signature.getInstance("SHA256withECDSA");sig.initSign(pc.getPrivate());sig.update(raw);byte[] signature=sig.sign();out.writeByte(signature.length);out.write(signature);return b.toByteArray();
    }
    byte[] beginBody()throws Exception {
        ByteArrayOutputStream b=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(b);
        out.writeLong(data.length);out.write(OpticalReceiver.hexBytes(Util.hash(data)));out.writeBytes(keyId);out.write(new byte[16]);
        byte[] label="4色試験".getBytes(StandardCharsets.UTF_8);out.writeShort(label.length);out.write(label);return b.toByteArray();
    }
    void begin()throws Exception{assertEquals("ack",response(receiver.accept(frame(0,0,beginBody()))).getString("code"));}
    byte[] block(int seq){return Arrays.copyOfRange(data,(seq-1)*1024,Math.min(data.length,seq*1024));}
    JSONObject poll(int base,int token)throws Exception {
        ByteArrayOutputStream b=new ByteArrayOutputStream();new DataOutputStream(b).writeInt(token);
        return response(receiver.accept(frame(2,base,b.toByteArray())));
    }
    JSONObject response(String text)throws Exception {
        assertTrue(text.startsWith("C71A2:"));String[] parts=text.substring(6).split("\\.");byte[] raw=Util.un64(parts[0]);assertTrue(raw.length==51||raw.length==83);
        Signature s=Signature.getInstance("SHA256withECDSA");s.initVerify(vault.publicKey);s.update(raw);assertTrue(s.verify(Util.un64(parts[1])));
        DataInputStream in=new DataInputStream(new ByteArrayInputStream(raw));assertEquals(2,in.readByte());in.skipBytes(32);
        int base=in.readInt(),token=in.readInt(),mask=in.readUnsignedByte(),code=in.readUnsignedByte();long bytes=in.readLong();
        return new JSONObject().put("base",base).put("token",token).put("mask",mask).put("code",OpticalReceiver.CODES[code]).put("bytes",bytes);
    }
    @Test public void selectiveRepeatAndCommitOnlyAfterEnd()throws Exception {
        begin();String ack=receiver.previousReply;
        for(int seq:new int[]{8,1,7,3,4,6,5})assertEquals(ack,receiver.accept(frame(1,seq,block(seq))));
        JSONObject partial=poll(1,123);assertEquals(253,partial.getInt("mask"));assertEquals(7*1024,partial.getLong("bytes"));assertEquals(0,receiver.temporary.length());
        receiver.accept(frame(1,2,block(2)));JSONObject full=poll(1,124);assertEquals(255,full.getInt("mask"));assertEquals(8192,receiver.temporary.length());
        assertEquals(125,poll(1,125).getInt("token"));assertEquals(8192,receiver.temporary.length());
        receiver.accept(frame(1,1,block(1)));assertEquals(8192,receiver.temporary.length());
        receiver.accept(frame(1,10,block(10)));receiver.accept(frame(1,9,block(9)));assertEquals(3,poll(9,126).getInt("mask"));
        assertFalse(new File(vault.archives,id).exists());
        byte[] end=frame(3,11,new byte[0]);String result=receiver.accept(end);
        assertEquals("stored",response(result).getString("code"));assertEquals(result,receiver.accept(end));
        assertEquals(Util.hash(data),Util.hash(new File(vault.archives,id+"/data.c71b")));
    }
    @Test public void missingFramesCannotCommit()throws Exception {
        begin();receiver.accept(frame(1,1,block(1)));assertEquals(1,poll(1,42).getInt("mask"));
        assertEquals("sequence",response(receiver.accept(frame(3,11,new byte[0]))).getString("code"));assertFalse(new File(vault.archives,id).exists());
    }
    @Test public void conflictingDuplicateRejected()throws Exception {
        begin();receiver.accept(frame(1,1,block(1)));byte[] changed=block(1);changed[0]^=1;
        assertEquals("invalid",response(receiver.accept(frame(1,1,changed))).getString("code"));assertArrayEquals(block(1),receiver.blocks[0]);
    }
    @Test public void staleSessionsTransfersAndTamperCannotChangeState()throws Exception {
        String ready=receiver.previousReply;
        assertEquals(ready,receiver.accept(frame(0,0,beginBody(),"0".repeat(32),id)));
        byte[] bad=frame(0,0,beginBody());bad[80]^=1;
        try{receiver.accept(bad);fail();}catch(Exception expected){}assertNull(receiver.begin);
        begin();assertEquals(receiver.previousReply,receiver.accept(frame(1,1,block(1),receiver.session,"0".repeat(32))));assertEquals(0,receiver.mask);
    }
    @Test public void unknownOperationsAndOutsideWindowRejected()throws Exception {
        begin();assertEquals("forbidden",response(receiver.accept(frame(99,1,new byte[0]))).getString("code"));
        assertEquals("sequence",response(receiver.accept(frame(1,9,block(9)))).getString("code"));
        assertEquals("invalid",response(receiver.accept(frame(1,1,new byte[1023]))).getString("code"));assertEquals(0,receiver.mask);
    }
    @Test public void keyCustodyAndQuotaRequired()throws Exception {
        new File(vault.base,"recovery-keys/"+keyId+".json").delete();
        assertEquals("key_missing",response(receiver.accept(frame(0,0,beginBody()))).getString("code"));assertNull(receiver.begin);
        Util.atomicJson(new File(vault.base,"recovery-keys/"+keyId+".json"),new JSONObject().put("fixture",true));
        long old=vault.quota;try{vault.quota=0;assertEquals("capacity",response(receiver.accept(frame(0,0,beginBody()))).getString("code"));assertNull(receiver.begin);}finally{vault.quota=old;}
    }
    @Test public void closeRemovesPartialAndRejectsFurtherFrames()throws Exception {
        begin();receiver.close();assertFalse(receiver.temporary.exists());
        try{receiver.accept(frame(1,1,block(1)));fail();}catch(IOException expected){}
    }
    byte[] asset(String name)throws Exception {
        try(InputStream in=InstrumentationRegistry.getInstrumentation().getContext().getAssets().open(name)){return in.readAllBytes();}
    }
    @Test public void pythonColorImageDecodesToExactBinaryPacket()throws Exception {
        byte[] raw=asset("color-packet.bin"),png=asset("color-frame.png");Bitmap image=BitmapFactory.decodeByteArray(png,0,png.length);
        int[] pixels=new int[image.getWidth()*image.getHeight()];image.getPixels(pixels,0,image.getWidth(),0,0,image.getWidth(),image.getHeight());
        assertArrayEquals(raw,ColorCode.decodePixels(pixels,image.getWidth(),image.getHeight()));image.recycle();
    }
    @Test public void cameraNv21SubsamplingDecodesPythonColorImage()throws Exception {
        assertArrayEquals(asset("color-packet.bin"),ColorCode.decodeNv21(asset("color-frame.nv21"),630,630));
    }
    @Test public void pythonSignatureVerifiesOnAndroid()throws Exception {
        byte[] raw=asset("color-packet.bin");PublicKey key=KeyFactory.getInstance("EC").generatePublic(new java.security.spec.X509EncodedKeySpec(asset("color-public.der")));
        int end=75+1024;Signature verifier=Signature.getInstance("SHA256withECDSA");verifier.initVerify(key);verifier.update(raw,0,end);assertTrue(verifier.verify(Arrays.copyOfRange(raw,end+1,raw.length)));
    }
}
