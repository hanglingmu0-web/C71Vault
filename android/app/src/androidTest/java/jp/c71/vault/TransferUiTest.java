package jp.c71.vault;

import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.*;
import org.json.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.*;
import static org.junit.Assert.*;

public class TransferUiTest {
    Vault vault;String previous,names;
    @Before public void setup()throws Exception{vault=Vault.get(InstrumentationRegistry.getInstrumentation().getTargetContext());previous=vault.selectedFolder();names=vault.context.getSharedPreferences("settings",0).getString("receive_folders","[\"未分類\"]");}
    @After public void restore(){vault.context.getSharedPreferences("settings",0).edit().putString("receive_folder",previous).putString("receive_folders",names).commit();}
    @Test public void localFolderSelectionAndBounds()throws Exception{
        vault.selectFolder("仕事用の資料");assertEquals("仕事用の資料",vault.selectedFolder());
        int count=vault.folderNames().length();vault.selectFolder("仕事用の資料");assertEquals(count,vault.folderNames().length());
        for(String bad:new String[]{"", "../x", "a/b", "a\\b", "..", "x\ny"}){try{vault.selectFolder(bad);fail(bad);}catch(IOException expected){}}
    }
    JSONObject decode(byte[] wire)throws Exception{
        assertEquals('A',wire[4]);assertEquals(0xf0,wire[0]&255);ByteArrayOutputStream out=new ByteArrayOutputStream();
        for(int p=5;p<wire.length-1;p+=8){int count=Math.min(7,wire.length-2-p),mask=wire[p];for(int i=0;i<count;i++)out.write(wire[p+1+i]|(((mask>>i)&1)<<7));}
        JSONObject env=new JSONObject(out.toString("UTF-8"));byte[] raw=Util.un64(env.getString("payload"));Signature s=Signature.getInstance("SHA256withECDSA");s.initVerify(vault.publicKey);s.update(raw);assertTrue(s.verify(Util.un64(env.getString("signature"))));return new JSONObject(new String(raw,StandardCharsets.UTF_8));
    }
    @Test public void signedAckOnlyClaimsCommitAfterStorage()throws Exception{
        IsolatedReceiver r=new IsolatedReceiver(x->{},vault);byte[] session=new byte[16];session[0]=1;
        SerialFrame end=new SerialFrame(4,session,5,new byte[0]);r.complete=true;r.received=900;r.sha256="a".repeat(64);
        JSONObject p=decode(MidiReceipt.encode(vault,end,r,true));assertEquals("verified",p.getString("code"));assertFalse(p.has("sha256"));
        r.committed=true;p=decode(MidiReceipt.encode(vault,end,r,true));assertEquals("committed",p.getString("code"));assertEquals(r.sha256,p.getString("sha256"));assertEquals(5,p.getInt("sequence"));
        p=decode(MidiReceipt.encode(vault,end,r,false));assertEquals("error",p.getString("code"));assertFalse(p.has("sha256"));assertFalse(p.has("files"));assertFalse(p.has("key"));
    }
}
