package jp.c71.vault;

import android.content.Context;
import android.os.StatFs;
import android.security.keystore.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import java.security.spec.*;
import java.util.*;
import org.json.*;

final class Vault {
    static Vault instance;
    static synchronized Vault get(Context c)throws Exception { if(instance==null)instance=new Vault(c.getApplicationContext());return instance; }
    final Context context; final File base,archives; final PrivateKey signing; final PublicKey publicKey;
    final String device; JSONObject clients; volatile String status="受付は停止中です";
    final Map<String,JSONObject> pending=new java.util.concurrent.ConcurrentHashMap<>();
    final Map<String,Long> ackExpiry=new HashMap<>();
    final Map<String,JSONObject> keyRequests=new java.util.concurrent.ConcurrentHashMap<>();
    final Map<String,JSONObject> keyResults=new java.util.concurrent.ConcurrentHashMap<>();
    RecoveryKeys recovery;
    long quota=40*Util.GIB,reserve=8*Util.GIB,maxArchive=8*Util.GIB;
    Vault(Context c)throws Exception {
        context=c;base=new File(c.getFilesDir(),"vault");archives=new File(base,"archives");if(!archives.mkdirs()&&!archives.isDirectory())throw new IOException("保存領域を作れません");
        String d=c.getSharedPreferences("settings",0).getString("device",null);if(d==null){d=UUID.randomUUID().toString();c.getSharedPreferences("settings",0).edit().putString("device",d).commit();}device=d;
        KeyStore ks=KeyStore.getInstance("AndroidKeyStore");ks.load(null);String alias="C71VaultReceipt";
        if(!ks.containsAlias(alias)){KeyPairGenerator g=KeyPairGenerator.getInstance("EC","AndroidKeyStore");g.initialize(new KeyGenParameterSpec.Builder(alias,KeyProperties.PURPOSE_SIGN|KeyProperties.PURPOSE_VERIFY).setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1")).setDigests(KeyProperties.DIGEST_SHA256).build());g.generateKeyPair();}
        signing=(PrivateKey)ks.getKey(alias,null);publicKey=ks.getCertificate(alias).getPublicKey();
        File cf=new File(base,"clients.json");clients=cf.exists()?Util.json(cf):new JSONObject();
        for(File f:Objects.requireNonNull(archives.listFiles()))if(f.getName().startsWith(".pending-")||f.getName().startsWith(".deleting-"))Util.removeTemp(f);
    }
    String fingerprint()throws Exception{return Util.hash(publicKey.getEncoded());}
    synchronized RecoveryKeys recovery()throws Exception {if(recovery==null)recovery=new RecoveryKeys(context,base);return recovery;}
    java.time.ZoneId policyZone(){String z=context.getSharedPreferences("settings",0).getString("policy_zone",null);if(z==null){z=java.time.ZoneId.systemDefault().getId();context.getSharedPreferences("settings",0).edit().putString("policy_zone",z).commit();}return java.time.ZoneId.of(z);}
    synchronized JSONArray retentionPlan()throws Exception{return Retention.candidates(listing(""),System.currentTimeMillis(),policyZone());}
    synchronized void setImportant(String id,boolean value)throws Exception {File f=new File(new File(archives,Util.id(id)),"meta.json");JSONObject m=Util.json(f);m.put("important",value);Util.atomicJson(f,m);}
    synchronized int applyRetention(java.util.Set<String> selected)throws Exception {
        JSONArray current=retentionPlan();int deleted=0;
        for(int i=0;i<current.length();i++){String id=current.getJSONObject(i).getString("id");if(selected.contains(id)){deleteLocal(id);deleted++;}}
        status="確認済みの整理を実行しました: "+deleted+"件";return deleted;
    }
    synchronized void approveKey(String request)throws Exception {
        JSONObject q=keyRequests.get(request);if(q==null)throw new IOException("鍵の要求が見つかりません");
        String id=q.getString("key_id");JSONObject result;
        if(q.getString("op").equals("escrow")){recovery().approveImport(id,q.getString("capsule"));result=new JSONObject().put("key_id",id).put("custody_verified",true);}
        else result=new JSONObject().put("key_id",id).put("capsule",recovery().recoverFor(id,q.getString("recipient")));
        keyResults.put(request,result);keyRequests.remove(request);status="復元鍵の端末認証が完了しました";
    }
    // Invoked only by MainActivity after Android's device-credential confirmation.
    synchronized void deleteLocal(String archiveId)throws Exception {
        String id=Util.id(archiveId);File d=new File(archives,id);if(!d.isDirectory())throw new IOException("保存データが見つかりません");
        if(Util.json(new File(d,"meta.json")).optBoolean("important",false))throw new IOException("重要な版は削除できません。先に端末認証で重要指定を解除してください");
        File tomb=new File(archives,".deleting-"+id);Files.move(d.toPath(),tomb.toPath(),StandardCopyOption.ATOMIC_MOVE);Util.syncDir(archives);Util.removeTemp(tomb);Util.syncDir(archives);status="端末認証後、選択した版を削除しました";
    }
    JSONObject envelope(JSONObject p)throws Exception { byte[] b=p.toString().getBytes(StandardCharsets.UTF_8);Signature s=Signature.getInstance("SHA256withECDSA");s.initSign(signing);s.update(b);return new JSONObject().put("payload",Util.b64(b)).put("signature",Util.b64(s.sign())); }
    JSONObject info()throws Exception{
        JSONObject i=new JSONObject().put("version",1).put("device",device).put("public_key",Util.b64(publicKey.getEncoded())).put("fingerprint",fingerprint()).put("transport","mtp-folder");
        try{byte[] pub=recovery().publicBytes();Signature s=Signature.getInstance("SHA256withECDSA");s.initSign(signing);s.update(pub);i.put("recovery_public_key",Util.b64(pub)).put("recovery_key_signature",Util.b64(s.sign()));}catch(Exception e){i.put("recovery_unavailable",true);}
        return i;
    }
    synchronized void approve(String fp)throws Exception {JSONObject p=pending.get(fp);if(p==null)throw new IOException("登録要求がありません");clients.put(fp,p);Util.atomicJson(new File(base,"clients.json"),clients);pending.remove(fp);status="PCを登録しました";}
    static PublicKey decodeKey(String b)throws Exception {PublicKey k=KeyFactory.getInstance("EC").generatePublic(new X509EncodedKeySpec(Util.un64(b)));if(!(k instanceof java.security.interfaces.ECPublicKey e)||e.getParams().getCurve().getField().getFieldSize()!=256)throw new IOException("PC鍵が不正です");return k;}
    static JSONObject verify(JSONObject e,PublicKey key)throws Exception {byte[] b=Util.un64(e.getString("payload"));if(b.length>32768)throw new IOException("要求が大きすぎます");Signature s=Signature.getInstance("SHA256withECDSA");s.initVerify(key);s.update(b);if(!s.verify(Util.un64(e.getString("signature"))))throw new IOException("PCの署名が一致しません");return new JSONObject(new String(b,StandardCharsets.UTF_8));}
    String selectedFolder(){return context.getSharedPreferences("settings",0).getString("receive_folder","未分類");}
    synchronized void selectFolder(String name)throws Exception {
        if(name==null||name.isBlank()||name.length()>60||name.chars().anyMatch(c->c<32)||name.contains("/")||name.contains("\\")||name.equals(".")||name.equals(".."))throw new IOException("フォルダ名は区切り文字を含めず1～60文字で指定してください");
        JSONArray names=folderNames();boolean exists=false;for(int i=0;i<names.length();i++)exists|=names.getString(i).equals(name);
        if(!exists){if(names.length()>=100)throw new IOException("保存フォルダは100個までです");names.put(name);}
        if(!context.getSharedPreferences("settings",0).edit().putString("receive_folder",name).putString("receive_folders",names.toString()).commit())throw new IOException("設定を保存できません");
    }
    JSONArray folderNames()throws Exception{return new JSONArray(context.getSharedPreferences("settings",0).getString("receive_folders","[\"未分類\"]"));}
    synchronized JSONArray listing(String client)throws Exception {JSONArray a=new JSONArray();File[] ds=archives.listFiles();if(ds!=null){Arrays.sort(ds,Comparator.comparing(File::getName));for(File d:ds)if(d.getName().matches("[0-9a-f]{32}")){JSONObject m=Util.json(new File(d,"meta.json"));a.put(m);}}return a;}
    synchronized JSONObject store(JSONObject q, InputStream incoming)throws Exception {
        String id=Util.id(q.getString("id")),hash=q.getString("sha256"),client=q.getString("client");long expected=q.getLong("bytes");
        if(!hash.matches("[0-9a-f]{64}")||expected<64||expected>maxArchive)throw new IOException("サイズまたはハッシュが不正です（1回の上限8GiB）");
        File dest=new File(archives,id);
        if(dest.exists()){JSONObject old=Util.json(new File(dest,"meta.json"));if(old.getString("sha256").equals(hash)&&old.getString("client").equals(client)&&old.getLong("bytes")==expected)return old;throw new IOException("保存済みIDへの上書きは禁止です");}
        if(Util.size(archives)+expected+65536>quota)throw new IOException("保存上限です。旧版を残し、新規保存を停止しました");
        if(new StatFs(base.getPath()).getAvailableBytes()-expected<reserve)throw new IOException("端末の空き容量不足です。旧版は削除しません");
        File temp=new File(archives,".pending-"+id);if(temp.exists())Util.removeTemp(temp);if(!temp.mkdir())throw new IOException("一時領域を作れません");
        try {
            File data=new File(temp,"data.c71b");MessageDigest md=MessageDigest.getInstance("SHA-256");long count=0;
            try(FileOutputStream out=new FileOutputStream(data)){byte[] b=new byte[262144];int n;while((n=incoming.read(b))!=-1){count+=n;if(count>expected)throw new IOException("宣言サイズを超えています");out.write(b,0,n);md.update(b,0,n);}out.getFD().sync();}
            if(count!=expected||!Util.hex(md.digest()).equals(hash))throw new IOException("転送データが一致しません。保存を確定しませんでした");
            // Validate only the bounded, public header. Plaintext and the recovery key never enter the phone.
            try(DataInputStream in=new DataInputStream(new FileInputStream(data))){byte[] magic=new byte[10];in.readFully(magic);if(!Arrays.equals(magic,"C71VAULT1\n".getBytes(StandardCharsets.US_ASCII)))throw new IOException("バックアップ形式が違います");int len=in.readInt();if(len<2||len>1024)throw new IOException("ヘッダー長が不正です");byte[] h=new byte[len];in.readFully(h);JSONObject header=new JSONObject(new String(h,StandardCharsets.UTF_8));if(header.getInt("version")!=1||Util.un64(header.getString("salt")).length!=16||Util.un64(header.getString("nonce")).length!=12||!header.getString("key_id").equals(q.getString("key_id")))throw new IOException("暗号形式が不正です");}
            if(!Util.hash(data).equals(hash))throw new IOException("保存後の読み戻し検証に失敗しました");
            String label=q.optString("label","バックアップ");if(label.length()>100||label.chars().anyMatch(x->x<32))throw new IOException("ラベルが不正です");
            JSONObject m=new JSONObject().put("id",id).put("client",client).put("sha256",hash).put("bytes",expected).put("key_id",q.getString("key_id")).put("label",label).put("stored_at",System.currentTimeMillis()).put("device",device);
            String series=q.optString("series","");if(!series.isEmpty())m.put("series",Util.id(series));m.put("important",false);m.put("folder",selectedFolder());
            Util.durable(new File(temp,"meta.json"),m.toString().getBytes(StandardCharsets.UTF_8));Util.syncDir(temp);
            Files.move(temp.toPath(),dest.toPath(),StandardCopyOption.ATOMIC_MOVE);Util.syncDir(archives);status="保存・読み戻し照合が完了しました";return m;
        }finally {if(temp.exists())Util.removeTemp(temp);}
    }
    synchronized void poll(Bridge b)throws Exception {
        Map<String,android.net.Uri> files=b.entries();
        for(var it=ackExpiry.entrySet().iterator();it.hasNext();){var x=it.next();if(android.os.SystemClock.elapsedRealtime()>x.getValue()){android.net.Uri u=files.get(x.getKey());if(u!=null)b.delete(u);it.remove();}}
        if(!files.containsKey("device.json"))b.write("device.json",info().toString().getBytes(StandardCharsets.UTF_8));
        int processed=0;
        for(var entry:files.entrySet()) {
            String name=entry.getKey();if(!name.matches("q-[0-9a-f]{32}\\.json")||processed++>=20)continue;String reqId=name.substring(2,34);
            try {
                JSONObject env=new JSONObject(new String(b.read(entry.getValue(),65536),StandardCharsets.UTF_8));
                JSONObject raw=new JSONObject(new String(Util.un64(env.getString("payload")),StandardCharsets.UTF_8));
                String client=raw.getString("client");PublicKey key;
                if(raw.optString("op").equals("pair")) {
                    key=decodeKey(raw.getString("public_key"));if(!Util.hash(key.getEncoded()).equals(client))throw new IOException("PC鍵IDが不正です");
                    JSONObject q=verify(env,key);if(!q.getString("request_id").equals(reqId))throw new IOException("要求IDが一致しません");
                    if(!clients.has(client)){if(pending.size()<8)pending.put(client,new JSONObject().put("public_key",raw.getString("public_key")).put("name",raw.optString("name","Windows PC").substring(0,Math.min(80,raw.optString("name","Windows PC").length()))));status="PC登録の確認待ちです";continue;}
                }else {if(!clients.has(client))throw new IOException("未登録のPCです");key=decodeKey(clients.getJSONObject(client).getString("public_key"));}
                JSONObject q=verify(env,key);if(!q.getString("request_id").equals(reqId))throw new IOException("要求IDが一致しません");
                JSONObject result;String op=q.getString("op");
                switch(op) {
                    case "escrow": case "recover_key": {
                        String id=RecoveryKeys.keyId(q.getString("key_id"));
                        if(op.equals("escrow")&&recovery().has(id)){result=new JSONObject().put("key_id",id).put("custody_verified",true);break;}
                        if(op.equals("recover_key")&&!recovery().has(id))throw new IOException("この復元鍵はC71に保管されていません");
                        JSONObject completed=keyResults.remove(reqId);
                        if(completed!=null){result=completed;break;}
                        if(keyRequests.size()>=8&&!keyRequests.containsKey(reqId))throw new IOException("端末確認待ちの鍵要求が多すぎます");
                        if(op.equals("escrow")&&Util.un64(q.getString("capsule")).length!=256)throw new IOException("鍵カプセルが不正です");
                        if(op.equals("recover_key")&&q.getString("recipient").length()>1024)throw new IOException("回収先の鍵が不正です");
                        keyRequests.putIfAbsent(reqId,q);status="C71で復元鍵の端末認証をしてください";continue;
                    }
                    case "ack": {
                        String target=Util.id(q.getString("target"));
                        for(String prefix:new String[]{"r-","x-"}){android.net.Uri u=files.get(prefix+target+(prefix.equals("r-")?".json":".c71b"));if(u!=null)b.delete(u);}
                        reply(b,reqId,true,"ack",new JSONObject().put("cleaned",true));ackExpiry.put("r-"+reqId+".json",android.os.SystemClock.elapsedRealtime()+60000);b.delete(entry.getValue());continue;
                    }
                    case "pair": result=new JSONObject().put("paired",true);break;
                    case "list": result=new JSONObject().put("archives",listing(client)).put("used_bytes",Util.size(archives)).put("quota_bytes",quota);break;
                    case "store": {
                        String id=Util.id(q.getString("id"));android.net.Uri data=files.get("b-"+id+".c71b");
                        if(data==null&&!new File(archives,id).exists())continue;
                        try(InputStream in=data==null?new ByteArrayInputStream(new byte[0]):b.input(data)){result=store(q,in);}
                        if(data!=null)b.delete(data);break;
                    }
                    case "export": {
                        String id=Util.id(q.getString("id"));File dir=new File(archives,id);JSONObject meta=Util.json(new File(dir,"meta.json"));
                        File data=new File(dir,"data.c71b");if(new StatFs(base.getPath()).getAvailableBytes()-data.length()<reserve)throw new IOException("書き出し用の空き容量がありません");if(!Util.hash(data).equals(meta.getString("sha256")))throw new IOException("保管データの破損を検出しました");
                        b.copyOut("x-"+reqId+".c71b",data);result=meta;break;
                    }
                    default: throw new IOException("許可されていない操作です。削除・上書きAPIはありません");
                }
                reply(b,reqId,true,q.getString("op"),result);b.delete(entry.getValue());
            }catch(Exception e){status="受付エラー: "+e.getMessage();reply(b,reqId,false,"error",new JSONObject().put("error",e.getMessage()==null?e.getClass().getSimpleName():e.getMessage()));b.delete(entry.getValue());}
        }
    }
    void reply(Bridge b,String id,boolean ok,String op,JSONObject result)throws Exception {JSONObject p=new JSONObject().put("request_id",id).put("ok",ok).put("op",op).put("result",result).put("device",device);b.write("r-"+id+".json",envelope(p).toString().getBytes(StandardCharsets.UTF_8));}
}
