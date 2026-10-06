package jp.c71.vault;

import android.app.*;
import android.content.*;
import android.os.*;

public class VaultService extends Service {
    static volatile boolean running;private volatile boolean stop;private Thread worker;private PowerManager.WakeLock lock;
    @Override public void onCreate(){super.onCreate();NotificationManager nm=getSystemService(NotificationManager.class);nm.createNotificationChannel(new NotificationChannel("receiver","USBバックアップ受付",NotificationManager.IMPORTANCE_LOW));
        PendingIntent pi=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_IMMUTABLE);
        startForeground(71,new Notification.Builder(this,"receiver").setSmallIcon(android.R.drawable.ic_lock_lock).setContentTitle("C71 Vault 受付中").setContentText("暗号化されたバックアップをUSB転送フォルダから受け付けています").setContentIntent(pi).build());
        lock=getSystemService(PowerManager.class).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK,"C71Vault:Receiver");running=true;
        worker=new Thread(()->{try{Vault v=Vault.get(this);String uri=getSharedPreferences("settings",0).getString("tree",null);if(uri==null)throw new IllegalStateException("転送フォルダを選んでください");Bridge b=new Bridge(this,uri);b.write("device.json",v.info().toString().getBytes(java.nio.charset.StandardCharsets.UTF_8));v.status="USB転送待ちです";
            while(!stop){try{lock.acquire(15*60*1000L);v.poll(b);}catch(Exception e){v.status="受付エラー: "+e.getMessage();}finally{if(lock.isHeld())lock.release();}Thread.sleep(2000);}
        }catch(InterruptedException ignored){}catch(Exception e){try{Vault.get(this).status=e.getMessage();}catch(Exception ignored){}}finally{running=false;stopSelf();}},"C71Vault receiver");worker.start();}
    @Override public int onStartCommand(Intent i,int f,int id){return START_NOT_STICKY;}
    @Override public void onDestroy(){stop=true;if(worker!=null)worker.interrupt();running=false;super.onDestroy();}
    @Override public IBinder onBind(Intent i){return null;}
}
