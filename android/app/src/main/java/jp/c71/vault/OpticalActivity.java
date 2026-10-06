package jp.c71.vault;

import android.app.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import android.content.pm.PackageManager;
import com.journeyapps.barcodescanner.*;
import com.journeyapps.barcodescanner.camera.CameraSettings;
import com.google.zxing.*;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class OpticalActivity extends Activity {
    BarcodeView camera;ImageView ack;TextView state;OpticalReceiver receiver;
    final ExecutorService executor=Executors.newSingleThreadExecutor();final AtomicBoolean busy=new AtomicBoolean();
    boolean closing;
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(12,52,12,55);body.setBackgroundColor(android.graphics.Color.WHITE);setContentView(body);
        state=new TextView(this);state.setTextSize(16);state.setTextColor(android.graphics.Color.BLACK);state.setText("上段のACKをPCカメラへ。下段は前面カメラの映像です。");body.addView(state);
        camera=new BarcodeView(this);CameraSettings settings=new CameraSettings();
        for(int i=0;i<android.hardware.Camera.getNumberOfCameras();i++){android.hardware.Camera.CameraInfo info=new android.hardware.Camera.CameraInfo();android.hardware.Camera.getCameraInfo(i,info);if(info.facing==android.hardware.Camera.CameraInfo.CAMERA_FACING_FRONT){settings.setRequestedCameraId(i);break;}}
        camera.setCameraSettings(settings);camera.setDecoderFactory(new DefaultDecoderFactory(Collections.singletonList(BarcodeFormat.QR_CODE)));
        camera.setPreviewScalingStrategy(new com.journeyapps.barcodescanner.camera.FitCenterStrategy());camera.setMarginFraction(0.0);
        ack=new ImageView(this);ack.setScaleType(ImageView.ScaleType.FIT_CENTER);body.addView(ack,new LinearLayout.LayoutParams(-1,0,1));
        ack.setContentDescription("上段：PCへ返すACKコード");
        camera.setContentDescription("下段：PCのコードを読むカメラ映像");
        body.addView(camera,new LinearLayout.LayoutParams(-1,0,1));
        Button close=new Button(this);close.setText("光学受付を終了");close.setOnClickListener(v->finish());body.addView(close);
        try{receiver=new OpticalReceiver(Vault.get(this));showAck(receiver.previousReply);}catch(Exception e){state.setText(e.getMessage());return;}
        camera.decodeContinuous(new BarcodeCallback(){public void barcodeResult(BarcodeResult r){
            if(closing||!busy.compareAndSet(false,true))return;
            executor.execute(()->{try{String response=receiver.accept(r.getText());runOnUiThread(()->showAck(response));}catch(Exception e){runOnUiThread(()->state.setText("読み取りを再試行します。保存完了の通知が出るまでは未完了です。"));}finally{busy.set(false);}});
        }});
        if(checkSelfPermission("android.permission.CAMERA")!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{"android.permission.CAMERA"},80);
    }
    void showAck(String response){if(closing)return;try{
        ack.setImageBitmap(new BarcodeEncoder().encodeBitmap(response,BarcodeFormat.QR_CODE,640,640));
        if(receiver.complete)state.setText("保存完了・読み戻し照合済み。PCが完了を確認するまで、この画面を保持してください。");
        else state.setText("光学受付："+receiver.received+" bytes\n戻りはACK・状態のみ。復元はUSBを使用します。");
    }catch(Exception e){state.setText("ACKを表示できません");}}
    @Override protected void onResume(){super.onResume();if(camera!=null&&checkSelfPermission("android.permission.CAMERA")==PackageManager.PERMISSION_GRANTED)camera.resume();}
    @Override protected void onPause(){if(camera!=null)camera.pause();super.onPause();}
    @Override public void onRequestPermissionsResult(int r,String[] p,int[] g){super.onRequestPermissionsResult(r,p,g);if(r==80&&g.length>0&&g[0]==PackageManager.PERMISSION_GRANTED)camera.resume();}
    @Override public void onDestroy(){closing=true;executor.execute(()->{try{if(receiver!=null)receiver.close();}catch(Exception ignored){}});executor.shutdown();super.onDestroy();}
}
