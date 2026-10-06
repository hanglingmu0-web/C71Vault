package jp.c71.vault;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.*;
import org.junit.runner.RunWith;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.security.*;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public class VaultTest {
    Vault v;String id;byte[] bytes;JSONObject q;
    @Before public void setUp()throws Exception{
        v=Vault.get(InstrumentationRegistry.getInstrumentation().getTargetContext());id=UUID.randomUUID().toString().replace("-","");
        JSONObject h=new JSONObject().put("version",1).put("salt",Util.b64(new byte[16])).put("nonce",Util.b64(new byte[12])).put("key_id","0123456789abcdef");
        ByteArrayOutputStream b=new ByteArrayOutputStream();DataOutputStream out=new DataOutputStream(b);out.write("C71VAULT1\n".getBytes(StandardCharsets.US_ASCII));byte[] header=h.toString().getBytes(StandardCharsets.UTF_8);out.writeInt(header.length);out.write(header);out.write(new byte[100]);bytes=b.toByteArray();
        q=new JSONObject().put("id",id).put("client","test-client").put("bytes",bytes.length).put("sha256",Util.hash(bytes)).put("key_id","0123456789abcdef").put("label","試験用");
    }
    @After public void reset(){v.quota=40*Util.GIB;v.reserve=8*Util.GIB;}
    @Test public void commitReadsBackAndIsIdempotent()throws Exception{JSONObject m=v.store(q,new ByteArrayInputStream(bytes));File data=new File(v.archives,id+"/data.c71b");assertEquals(q.getString("sha256"),Util.hash(data));assertEquals(m.toString(),v.store(q,new ByteArrayInputStream(bytes)).toString());}
    @Test public void overwriteRejectedAndOriginalPreserved()throws Exception{v.store(q,new ByteArrayInputStream(bytes));byte[] changed=bytes.clone();changed[changed.length-1]=1;q.put("sha256",Util.hash(changed));try{v.store(q,new ByteArrayInputStream(changed));fail();}catch(IOException expected){}assertEquals(Util.hash(bytes),Util.hash(new File(v.archives,id+"/data.c71b")));}
    @Test public void truncatedNeverCommitted()throws Exception{try{v.store(q,new ByteArrayInputStream(Arrays.copyOf(bytes,bytes.length-1)));fail();}catch(IOException expected){}assertFalse(new File(v.archives,id).exists());assertFalse(new File(v.archives,".pending-"+id).exists());}
    @Test public void wrongHashNeverCommitted()throws Exception{q.put("sha256","0".repeat(64));try{v.store(q,new ByteArrayInputStream(bytes));fail();}catch(IOException expected){}assertFalse(new File(v.archives,id).exists());}
    @Test public void quotaDoesNotEvictOldSnapshots()throws Exception{v.store(q,new ByteArrayInputStream(bytes));String old=id;v.quota=0;q.put("id",UUID.randomUUID().toString().replace("-",""));try{v.store(q,new ByteArrayInputStream(bytes));fail();}catch(IOException expected){}assertEquals(Util.hash(bytes),Util.hash(new File(v.archives,old+"/data.c71b")));}
    @Test public void freeSpaceReserveRejects()throws Exception{v.reserve=Long.MAX_VALUE;try{v.store(q,new ByteArrayInputStream(bytes));fail();}catch(IOException expected){}assertFalse(new File(v.archives,id).exists());}
    @Test public void pathTraversalRejected()throws Exception{q.put("id","../../escape");try{v.store(q,new ByteArrayInputStream(bytes));fail();}catch(IOException expected){} }
    @Test public void receiptSignatureAndTamper()throws Exception{JSONObject p=new JSONObject().put("value","confirmed");JSONObject env=v.envelope(p);assertEquals("confirmed",Vault.verify(env,v.publicKey).getString("value"));env.put("payload",Util.b64("{\"value\":\"forged\"}".getBytes(StandardCharsets.UTF_8)));try{Vault.verify(env,v.publicKey);fail();}catch(IOException expected){} }
    @Test public void interruptedReadNeverCommitted()throws Exception{InputStream bad=new InputStream(){int count=0;public int read()throws IOException{if(count==50)throw new IOException("simulated disconnect");return count<bytes.length?bytes[count++]&255:-1;}};try{v.store(q,bad);fail();}catch(IOException expected){}assertFalse(new File(v.archives,id).exists());}
    @Test public void importantCannotBeDeleted()throws Exception{v.store(q,new ByteArrayInputStream(bytes));v.setImportant(id,true);try{v.deleteLocal(id);fail();}catch(IOException expected){}assertTrue(new File(v.archives,id).exists());v.setImportant(id,false);v.deleteLocal(id);assertFalse(new File(v.archives,id).exists());}
    @Test public void retentionRechecksImportanceAndKeepsLatest()throws Exception{
        String series=UUID.randomUUID().toString().replace("-","");q.put("series",series);v.store(q,new ByteArrayInputStream(bytes));String old=id;
        File meta=new File(v.archives,old+"/meta.json");JSONObject m=Util.json(meta).put("stored_at",System.currentTimeMillis()-70L*86400000);Util.atomicJson(meta,m);
        id=UUID.randomUUID().toString().replace("-","");q.put("id",id);v.store(q,new ByteArrayInputStream(bytes));File meta2=new File(v.archives,id+"/meta.json");JSONObject m2=Util.json(meta2).put("stored_at",m.getLong("stored_at")+1000);Util.atomicJson(meta2,m2);
        JSONArray plan=v.retentionPlan();assertTrue(plan.toString().contains(old));v.setImportant(old,true);assertEquals(0,v.applyRetention(Set.of(old)));assertTrue(new File(v.archives,old).exists());v.setImportant(old,false);assertEquals(1,v.applyRetention(Set.of(old)));assertTrue(new File(v.archives,id).exists());
    }
}
