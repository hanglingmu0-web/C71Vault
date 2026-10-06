package jp.c71.vault;

import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.net.Uri;
import android.os.*;
import android.provider.*;
import android.view.*;
import android.widget.*;
import java.util.*;
import org.json.*;

public class MainActivity extends Activity {
    LinearLayout body,requests; TextView status,capacity; Vault vault;
    Spinner folderChoice,transportChoice,opticalChoice;Button folderAdd;
    Handler handler=new Handler(); String lastRequests=""; Action afterAuth;
    interface Action {void run() throws Exception;}
    final Runnable refresh=new Runnable(){public void run(){
        try{
            if(folderChoice!=null){folderChoice.setEnabled(!VaultService.running);folderAdd.setEnabled(!VaultService.running);transportChoice.setEnabled(!VaultService.running);}
            boolean debug=Settings.Global.getInt(getContentResolver(),Settings.Global.ADB_ENABLED,0)==1;
            status.setText((debug?"開発接続中：保護運用時はUSBデバッグをOFF\n":"")+(VaultService.running?"● USB受付中\n":"● USB停止中\n")+vault.status);
            StatFs fs=new StatFs(vault.base.getPath());int threshold=getSharedPreferences("settings",0).getInt("warning_percent",15);
            boolean low=Retention.needsAttention(fs.getAvailableBytes(),fs.getTotalBytes(),threshold);
            capacity.setText(String.format(Locale.JAPAN,"%s保管 %.2f / 40 GiB\n端末の空き %.1f GiB（%.1f%%）\n警告しきい値 %d%%：自動削除はしません",low?"整理が必要\n":"",Util.size(vault.archives)/(double)Util.GIB,fs.getAvailableBytes()/(double)Util.GIB,100.0*fs.getAvailableBytes()/fs.getTotalBytes(),threshold));
            capacity.setTextColor(low?Color.rgb(175,40,25):Color.rgb(25,43,63));
            String signature=vault.pending.keySet()+"/"+vault.keyRequests.keySet();
            if(!signature.equals(lastRequests)){lastRequests=signature;showRequests();}
        }catch(Exception e){status.setText(e.getMessage());}handler.postDelayed(this,1500);
    }};
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        try{vault=Vault.get(this);}catch(Exception e){error(e);return;}
        ScrollView sc=new ScrollView(this);body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(28,60,28,65);body.setBackgroundColor(Color.rgb(244,247,251));sc.addView(body);setContentView(sc);
        body.addView(text("C71 Vault "+(BuildConfig.DEBUG?"開発版 ":"")+BuildConfig.VERSION_NAME,28));status=text("準備中",17);capacity=text("",14);body.addView(status);body.addView(capacity);
        requests=new LinearLayout(this);requests.setOrientation(LinearLayout.VERTICAL);body.addView(requests);
        body.addView(text("1  保存フォルダ",20));
        folderChoice=new Spinner(this);body.addView(folderChoice);reloadFolders();
        folderAdd=button("保存フォルダを作成",()->{
            if(VaultService.running)throw new Exception("受信を停止してから変更してください");
            EditText input=new EditText(this);input.setSingleLine(true);
            new AlertDialog.Builder(this).setTitle("アプリ内の保存フォルダ").setView(input).setPositiveButton("作成",(d,w)->{try{vault.selectFolder(input.getText().toString().trim());reloadFolders();}catch(Exception e){error(e);}}).setNegativeButton("戻る",null).show();
        });body.addView(folderAdd);
        body.addView(text("暗号化バックアップをアプリ専用領域内のフォルダ別に保管します。PCから保存先を変更できません。",14));
        body.addView(text("2  受信方法",20));
        transportChoice=new Spinner(this);transportChoice.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"USB","2次元コード","MIDI"}));body.addView(transportChoice);
        opticalChoice=new Spinner(this);opticalChoice.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"白黒","4色"}));opticalChoice.setVisibility(View.GONE);body.addView(opticalChoice);
        transportChoice.setOnItemSelectedListener(new android.widget.AdapterView.OnItemSelectedListener(){public void onNothingSelected(android.widget.AdapterView<?> p){}public void onItemSelected(android.widget.AdapterView<?> p,View v,int pos,long id){opticalChoice.setVisibility(pos==1?View.VISIBLE:View.GONE);}});
        body.addView(button("受信開始",this::startReceiving));
        body.addView(button("受信停止",()->stopService(new Intent(this,VaultService.class))));
        body.addView(button("USB受渡しフォルダの設定（初回）",()->{Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);i.putExtra(DocumentsContract.EXTRA_INITIAL_URI,Uri.parse("content://com.android.externalstorage.documents/document/primary%3ADocuments%2FC71Vault"));startActivityForResult(i,71);}));
        body.addView(button("保存一覧・重要指定・個別削除",this::showArchives));
        body.addView(button("保持ルールで整理候補を確認",this::showRetention));
        body.addView(button("空き容量の警告しきい値",this::warningSetting));
        body.addView(text("30日分は全版保持。その後は日・週・月ごとに保持。重要な版と対象ごとの最新版は整理しません。",14));
        try{TextView f=text("端末の署名鍵\n"+vault.fingerprint(),12);f.setTextIsSelectable(true);body.addView(f);}catch(Exception e){error(e);}
        body.addView(text("復元鍵は端末認証を必要とする鍵で暗号化し、専用領域に保管します。回収はこの端末で承認し、USB経由で行います。\n\nデータ消去・初期化・故障では、保管データと鍵を失います。別のバックアップも保持してください。",14));handler.post(refresh);
    }
    void reloadFolders(){try{JSONArray names=vault.folderNames();ArrayList<String> list=new ArrayList<>();int chosen=0;for(int i=0;i<names.length();i++){list.add(names.getString(i));if(names.getString(i).equals(vault.selectedFolder()))chosen=i;}folderChoice.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,list));folderChoice.setSelection(chosen);}catch(Exception e){error(e);}}
    void startReceiving()throws Exception {
        if(VaultService.running)throw new Exception("USB受信中です。変更する場合は受信停止を押してください");
        vault.selectFolder(folderChoice.getSelectedItem().toString());int mode=transportChoice.getSelectedItemPosition();
        if(mode==0){
            if(getSharedPreferences("settings",0).getString("tree",null)==null)throw new Exception("初回はUSB受渡しフォルダに Documents / C71Vault を設定してください");
            if(Build.VERSION.SDK_INT>=33&&checkSelfPermission("android.permission.POST_NOTIFICATIONS")!=android.content.pm.PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{"android.permission.POST_NOTIFICATIONS"},72);
            startForegroundService(new Intent(this,VaultService.class));
        }else if(mode==1)startActivity(new Intent(this,opticalChoice.getSelectedItemPosition()==0?OpticalActivity.class:ColorOpticalActivity.class));
        else startActivity(new Intent(this,IsolatedSerialActivity.class).putExtra("auto_start",true));
    }
    void showRequests()throws Exception{
        requests.removeAllViews();
        for(String fp:vault.pending.keySet()){
            JSONObject q=vault.pending.get(fp);if(q==null)continue;
            requests.addView(text("PC登録要求："+q.optString("name")+"\n"+fp,12));
            requests.addView(button("このPCを登録",()->new AlertDialog.Builder(this).setTitle("PC鍵を照合").setMessage("PCの表示と一致することを確認してください。\n"+fp).setPositiveButton("登録",(d,w)->background(()->vault.approve(fp))).setNegativeButton("戻る",null).show()));
        }
        for(String id:vault.keyRequests.keySet()){
            JSONObject q=vault.keyRequests.get(id);if(q==null)continue;boolean importing=q.getString("op").equals("escrow");String title=importing?"復元鍵をC71に保管":"復元鍵をPCへ回収";
            requests.addView(text(title+"\n鍵ID："+q.getString("key_id")+"\nPC鍵："+q.getString("client"),12));
            requests.addView(button(title+"（端末認証）",()->authenticate(title,importing?"暗号化された復元鍵を検証して保管します。":"初期化・駆除済みのPCであることを確認してください。鍵を要求元PCだけが読める形でUSB転送します。",()->vault.approveKey(id))));
        }
    }
    void authenticate(String title,String detail,Action action)throws Exception{
        KeyguardManager km=getSystemService(KeyguardManager.class);if(!km.isDeviceSecure())throw new Exception("端末にPIN等の画面ロックを設定してください");
        Intent i=km.createConfirmDeviceCredentialIntent(title,detail);if(i==null)throw new Exception("端末認証を開始できません");afterAuth=action;startActivityForResult(i,74);
    }
    void background(Action action){new Thread(()->{try{action.run();}catch(Exception e){runOnUiThread(()->error(e));}},"Vault local action").start();}
    TextView text(String s,int size){TextView t=new TextView(this);t.setText(s);t.setTextSize(size);t.setTextColor(Color.rgb(25,43,63));t.setPadding(0,12,0,12);return t;}
    Button button(String s,Action a){Button b=new Button(this);b.setText(s);b.setAllCaps(false);b.setOnClickListener(v->{try{a.run();}catch(Exception e){error(e);}});return b;}
    void error(Exception e){new AlertDialog.Builder(this).setTitle("確認してください").setMessage(e.getMessage()).setPositiveButton("閉じる",null).show();}
    String description(JSONObject m)throws Exception{return "［"+m.optString("folder","未分類")+"］"+(m.optBoolean("important")?"★ 重要　":"")+m.getString("label")+"\n"+new java.text.SimpleDateFormat("yyyy/MM/dd HH:mm",Locale.JAPAN).format(new Date(m.getLong("stored_at")))+String.format(Locale.JAPAN," / %.1f MiB",m.getLong("bytes")/1048576.0);}
    void showArchives(){background(()->{JSONArray all=vault.listing("");String[] labels=new String[all.length()];for(int i=0;i<all.length();i++)labels[i]=description(all.getJSONObject(i));runOnUiThread(()->new AlertDialog.Builder(this).setTitle("保管済みの版").setItems(labels,(d,w)->{try{manage(all.getJSONObject(w));}catch(Exception e){error(e);}}).setNegativeButton("閉じる",null).show());});}
    void manage(JSONObject m)throws Exception{
        String id=m.getString("id");boolean important=m.optBoolean("important");
        new AlertDialog.Builder(this).setTitle(description(m)).setMessage("鍵ID："+m.getString("key_id")+"\n重要な版は整理・削除の対象外です。")
        .setPositiveButton(important?"重要を解除（認証）":"重要にする",(d,w)->{try{if(important)authenticate("重要指定を解除","この版を削除可能にします",()->vault.setImportant(id,false));else background(()->vault.setImportant(id,true));}catch(Exception e){error(e);}})
        .setNeutralButton("個別削除（認証）",(d,w)->{try{if(important)throw new Exception("先に重要指定を解除してください");authenticate("選択した1版を削除","この版を削除します。保持ルールとは別の個別削除です。",()->vault.deleteLocal(id));}catch(Exception e){error(e);}}).setNegativeButton("閉じる",null).show();
    }
    void showRetention(){background(()->{
        JSONArray plan=vault.retentionPlan();String[] labels=new String[plan.length()];boolean[] checked=new boolean[plan.length()];Arrays.fill(checked,true);for(int i=0;i<plan.length();i++)labels[i]=description(plan.getJSONObject(i));
        runOnUiThread(()->{
            if(plan.length()==0){new AlertDialog.Builder(this).setMessage("整理候補はありません。重要・最新版・旧形式の版は保持します。自動削除はしません。").setPositiveButton("閉じる",null).show();return;}
            new AlertDialog.Builder(this).setTitle("整理候補 "+plan.length()+"件（まだ削除しません）").setMultiChoiceItems(labels,checked,(d,w,c)->checked[w]=c)
            .setPositiveButton("選択した候補を確認",(d,w)->{try{
                Set<String> selected=new HashSet<>();long bytes=0;for(int i=0;i<checked.length;i++)if(checked[i]){selected.add(plan.getJSONObject(i).getString("id"));bytes+=plan.getJSONObject(i).getLong("bytes");}if(selected.isEmpty())return;
                String summary=selected.size()+"件 / "+String.format(Locale.JAPAN,"%.1f MiB",bytes/1048576.0)+" を削除します。実行時に重要指定と保持ルールを再確認します。";
                new AlertDialog.Builder(this).setTitle("整理を実行しますか").setMessage(summary).setPositiveButton("端末認証して実行",(x,y)->{try{authenticate("バックアップの整理",summary,()->vault.applyRetention(selected));}catch(Exception e){error(e);}}).setNegativeButton("戻る",null).show();
            }catch(Exception e){error(e);}}).setNegativeButton("閉じる",null).show();
        });
    });}
    void warningSetting(){EditText input=new EditText(this);input.setInputType(2);input.setText(String.valueOf(getSharedPreferences("settings",0).getInt("warning_percent",15)));new AlertDialog.Builder(this).setTitle("空き容量の警告%（1～50）").setView(input).setPositiveButton("保存",(d,w)->{try{int n=Integer.parseInt(input.getText().toString());if(n<1||n>50)throw new Exception("1～50を指定してください");getSharedPreferences("settings",0).edit().putInt("warning_percent",n).commit();}catch(Exception e){error(e);}}).setNegativeButton("戻る",null).show();}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);
        if(request==74){Action action=afterAuth;afterAuth=null;if(result==RESULT_OK&&action!=null)background(action);return;}
        if(request==71&&result==RESULT_OK&&data!=null){try{Uri u=data.getData();if(!"com.android.externalstorage.documents".equals(u.getAuthority())||!DocumentsContract.getTreeDocumentId(u).equals("primary:Documents/C71Vault"))throw new Exception("Documents / C71Vault を選んでください");getContentResolver().takePersistableUriPermission(u,Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION);getSharedPreferences("settings",0).edit().putString("tree",u.toString()).commit();vault.status="転送フォルダを設定しました";}catch(Exception e){error(e);}}
    }
    @Override public void onDestroy(){handler.removeCallbacks(refresh);super.onDestroy();}
}
