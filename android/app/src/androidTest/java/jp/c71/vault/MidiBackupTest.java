package jp.c71.vault;

import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.*;
import org.json.*;
import java.io.*;
import java.nio.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import java.security.spec.ECGenParameterSpec;
import java.util.*;
import static org.junit.Assert.*;

public class MidiBackupTest {
    Vault vault;IsolatedReceiver receiver;KeyPair pc;String client,key="c040c040c040c040",id;byte[] session,data;long quota,reserve;
    Set<String> created=new HashSet<>();
    @Before public void prepare()throws Exception{
        vault=Vault.get(InstrumentationRegistry.getInstrumentation().getTargetContext());quota=vault.quota;reserve=vault.reserve;
        KeyPairGenerator g=KeyPairGenerator.getInstance("EC");g.initialize(new ECGenParameterSpec("secp256r1"));pc=g.generateKeyPair();client=Util.hash(pc.getPublic().getEncoded());
        vault.clients.put(client,new JSONObject().put("public_key",Util.b64(pc.getPublic().getEncoded())).put("name","MIDI test"));
        File keys=new File(vault.base,"recovery-keys");keys.mkdirs();Util.atomicJson(new File(keys,key+".json"),new JSONObject().put("fixture",true));
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(bytes);out.writeBytes("C71VAULT1\n");
        byte[] h=new JSONObject().put("version",1).put("salt",Util.b64(new byte[16])).put("nonce",Util.b64(new byte[12])).put("key_id",key).toString().getBytes(StandardCharsets.UTF_8);out.writeInt(h.length);out.write(h);byte[] random=new byte[1100];new Random(7).nextBytes(random);out.write(random);data=bytes.toByteArray();newSession();
    }
    void newSession()throws Exception{if(receiver!=null)receiver.close();id=UUID.randomUUID().toString().replace("-","");created.add(id);session=OpticalReceiver.hexBytes(id);receiver=new IsolatedReceiver(r->{},vault);}
    @After public void cleanup()throws Exception{receiver.close();vault.quota=quota;vault.reserve=reserve;for(String id:created)if(new File(vault.archives,id).exists())vault.deleteLocal(id);vault.clients.remove(client);new File(vault.base,"recovery-keys/"+key+".json").delete();}
    SerialFrame frame(int type,long seq,byte[] body){return new SerialFrame(type,session,seq,body);}
    void send(SerialFrame f){byte[] b=f.wire();receiver.feed(b,b.length);}
    byte[] startPayload()throws Exception{
        ByteBuffer b=ByteBuffer.allocate(105);b.put((byte)1).putLong(data.length).put(OpticalReceiver.hexBytes(Util.hash(data))).put(OpticalReceiver.hexBytes(client)).put(key.getBytes(StandardCharsets.US_ASCII)).put(new byte[16]);
        Signature sig=Signature.getInstance("SHA256withECDSA");sig.initSign(pc.getPrivate());sig.update(MidiBackupSink.DOMAIN);sig.update(session);sig.update(b.array());byte[] s=sig.sign();return ByteBuffer.allocate(106+s.length).put(b.array()).put((byte)s.length).put(s).array();
    }
    void start()throws Exception{send(frame(1,0,new byte[0]));send(frame(2,0,startPayload()));}
    int sendData(byte[] bytes){int seq=1;for(int p=0;p<bytes.length;p+=512)send(frame(3,seq++,Arrays.copyOfRange(bytes,p,Math.min(bytes.length,p+512))));return seq;}
    void complete()throws Exception{start();int end=sendData(data);assertFalse(new File(vault.archives,id).exists());send(frame(4,end,new byte[0]));}
    @Test public void versionTwoLabelIsSignedAndSaved()throws Exception{
        byte[] old=startPayload(),label="仕事の文書".getBytes(StandardCharsets.UTF_8);
        ByteBuffer body=ByteBuffer.allocate(107+label.length);body.put(Arrays.copyOf(old,105));body.put(0,(byte)2);body.putShort((short)label.length).put(label);
        Signature sig=Signature.getInstance("SHA256withECDSA");sig.initSign(pc.getPrivate());sig.update(MidiBackupSink.DOMAIN);sig.update(session);sig.update(body.array());byte[] signature=sig.sign();
        byte[] payload=ByteBuffer.allocate(body.capacity()+1+signature.length).put(body.array()).put((byte)signature.length).put(signature).array();
        send(frame(1,0,new byte[0]));send(frame(2,0,payload));int end=sendData(data);send(frame(4,end,new byte[0]));
        assertTrue(receiver.committed);assertEquals("仕事の文書",Util.json(new File(vault.archives,id+"/meta.json")).getString("label"));
    }
    @Test public void authenticatedStoreReadbackAndRepeatEnd()throws Exception{complete();assertTrue(receiver.committed);assertEquals(Util.hash(data),Util.hash(new File(vault.archives,id+"/data.c71b")));long seq=receiver.sequence;send(frame(4,seq,new byte[0]));assertTrue(receiver.committed);assertEquals(0,receiver.errors);}
    @Test public void selectedLocalFolderStoredWithArchive()throws Exception{
        String old=vault.selectedFolder();String names=vault.context.getSharedPreferences("settings",0).getString("receive_folders","[\"未分類\"]");
        try{vault.selectFolder("試験用資料");complete();assertTrue(receiver.committed);assertEquals("試験用資料",Util.json(new File(vault.archives,id+"/meta.json")).getString("folder"));}
        finally{vault.context.getSharedPreferences("settings",0).edit().putString("receive_folder",old).putString("receive_folders",names).commit();}
    }
    @Test public void unregisteredSenderCannotCreateStage()throws Exception{vault.clients.remove(client);start();assertFalse(receiver.active);assertNull(receiver.sink);assertTrue(receiver.lastError.contains("unregistered"));}
    @Test public void changedStartSignatureRejected()throws Exception{byte[] p=startPayload();p[40]^=1;send(frame(1,0,new byte[0]));send(frame(2,0,p));assertFalse(receiver.active);assertTrue(receiver.lastError.contains("signature"));}
    @Test public void missingKeyCustodyRejected()throws Exception{new File(vault.base,"recovery-keys/"+key+".json").delete();start();assertFalse(receiver.active);assertTrue(receiver.lastError.contains("custody"));}
    @Test public void quotaAndDiskReserveFailWithoutDeletingOldVersion()throws Exception{
        complete();String old=id,hash=Util.hash(new File(vault.archives,old+"/data.c71b"));newSession();vault.quota=0;start();assertFalse(receiver.active);assertTrue(receiver.lastError.contains("capacity"));
        vault.quota=quota;newSession();vault.reserve=Long.MAX_VALUE;start();assertFalse(receiver.active);assertTrue(receiver.lastError.contains("reserve"));assertEquals(hash,Util.hash(new File(vault.archives,old+"/data.c71b")));
    }
    @Test public void disconnectDeletesOnlyStage()throws Exception{start();File stage=receiver.sink.staging;send(frame(3,1,Arrays.copyOf(data,512)));receiver.close();assertFalse(stage.exists());assertFalse(new File(vault.archives,id).exists());assertFalse(receiver.committed);}
    @Test public void badCrcDeletesStageAndCannotCommit()throws Exception{start();File stage=receiver.sink.staging;byte[] raw=frame(3,1,Arrays.copyOf(data,512)).raw();raw[29]^=1;byte[] bad=SerialFrame.sysex(raw);receiver.feed(bad,bad.length);assertEquals("CRC mismatch",receiver.lastError);assertFalse(stage.exists());assertFalse(receiver.committed);}
    @Test public void hashMismatchCannotCommit()throws Exception{start();byte[] changed=data.clone();changed[changed.length-1]^=1;int end=sendData(changed);send(frame(4,end,new byte[0]));assertFalse(receiver.committed);assertEquals("SHA-256 mismatch",receiver.lastError);assertFalse(new File(vault.archives,id).exists());}
    @Test public void invalidArchiveHeaderCannotCommit()throws Exception{data[0]^=1;complete();assertFalse(receiver.committed);assertFalse(new File(vault.archives,id).exists());}
    @Test public void stagingTamperingDetectedBeforeStore()throws Exception{start();int end=sendData(data);try(RandomAccessFile out=new RandomAccessFile(receiver.sink.staging,"rw")){out.seek(30);out.write(99);}send(frame(4,end,new byte[0]));assertFalse(receiver.committed);assertTrue(receiver.lastError.contains("staging"));assertFalse(new File(vault.archives,id).exists());}
    @Test public void repeatWholeTransferDoesNotCreateAnotherVersion()throws Exception{
        complete();long storedAt=Util.json(new File(vault.archives,id+"/meta.json")).getLong("stored_at");
        start();int end=sendData(data);send(frame(4,end,new byte[0]));assertTrue(receiver.committed);assertEquals(storedAt,Util.json(new File(vault.archives,id+"/meta.json")).getLong("stored_at"));
    }
}
