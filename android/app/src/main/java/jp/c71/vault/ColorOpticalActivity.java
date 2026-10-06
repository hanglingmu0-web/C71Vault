package jp.c71.vault;

import android.app.Activity;
import android.os.Bundle;
import android.content.pm.PackageManager;
import android.graphics.ImageFormat;
import android.view.WindowManager;
import android.widget.*;
import com.google.zxing.BarcodeFormat;
import com.journeyapps.barcodescanner.*;
import com.journeyapps.barcodescanner.camera.*;
import java.util.concurrent.*;

/** Independent camera flow for the four-color receiver. */
public class ColorOpticalActivity extends Activity {
    CameraPreview camera;ImageView ack;TextView status;
    ColorOpticalReceiver receiver;
    final ExecutorService worker=Executors.newSingleThreadExecutor();
    volatile boolean closing,paused=true;
    boolean inFlight;
    String displayed="";
    long frames,decoded,lastDiagnostic;
    @Override public void onCreate(Bundle state){
        super.onCreate(state);getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(12,52,12,55);body.setBackgroundColor(android.graphics.Color.WHITE);setContentView(body);
        status=new TextView(this);status.setTextSize(15);
        status.setText("4色光学受付：1画面1,024 bytes / 最大8枚まとめACK\n前面カメラへPCのコード全体を向けてください。");body.addView(status);
        camera=new CameraPreview(this);CameraSettings settings=new CameraSettings();
        for(int i=0;i<android.hardware.Camera.getNumberOfCameras();i++){
            android.hardware.Camera.CameraInfo info=new android.hardware.Camera.CameraInfo();android.hardware.Camera.getCameraInfo(i,info);
            if(info.facing==android.hardware.Camera.CameraInfo.CAMERA_FACING_FRONT){settings.setRequestedCameraId(i);break;}
        }
        camera.setCameraSettings(settings);camera.setPreviewScalingStrategy(new FitCenterStrategy(){
            @Override protected float getScore(Size size,Size desired){
                // Prefer real camera detail over a preview resolution matched to the small UI pane.
                int longSide=Math.max(size.width,size.height),shortSide=Math.min(size.width,size.height);
                return 1f/(1f+Math.abs(longSide-1920)+Math.abs(shortSide-1080));
            }
        });camera.setMarginFraction(0);
        ack=new ImageView(this);ack.setScaleType(ImageView.ScaleType.FIT_CENTER);body.addView(ack,new LinearLayout.LayoutParams(-1,0,1));
        ack.setContentDescription("上段：PCへ返すACKコード");
        camera.setContentDescription("下段：PCのコードを読むカメラ映像");
        body.addView(camera,new LinearLayout.LayoutParams(-1,0,1));
        Button close=new Button(this);close.setText("4色光学受付を終了");close.setOnClickListener(v->finish());body.addView(close);
        try{receiver=new ColorOpticalReceiver(Vault.get(this));showAck(receiver.previousReply);}catch(Exception e){status.setText("受付を開始できません: "+e.getMessage());return;}
        camera.addStateListener(new CameraPreview.StateListener(){
            public void previewSized(){}
            public void previewStarted(){next();}
            public void previewStopped(){}
            public void cameraClosed(){}
            public void cameraError(Exception error){status.setText("カメラを開始できません: "+error.getMessage());}
        });
        if(checkSelfPermission("android.permission.CAMERA")!=PackageManager.PERMISSION_GRANTED)requestPermissions(new String[]{"android.permission.CAMERA"},81);
    }
    void next(){
        if(closing||paused||inFlight||receiver==null||camera.getCameraInstance()==null||!camera.isPreviewActive())return;
        inFlight=true;
        camera.getCameraInstance().requestPreview(new PreviewCallback(){
            public void onPreview(SourceData data){
                if(closing)return;
                worker.execute(()->{
                    String response=null;
                    try{
                        frames++;
                        if(!paused&&data.getImageFormat()==ImageFormat.NV21){
                            byte[] packet=ColorCode.decodeNv21(data.getData(),data.getDataWidth(),data.getDataHeight());decoded++;
                            response=receiver.accept(packet);
                        }
                    }catch(Exception ignored){/* Failed reads never acknowledge new data. */}
                    long now=android.os.SystemClock.elapsedRealtime();
                    if(now-lastDiagnostic>5000){lastDiagnostic=now;android.util.Log.i("C71Color","frames="+frames+" decoded="+decoded+" size="+data.getDataWidth()+"x"+data.getDataHeight()+" format="+data.getImageFormat());}
                    final String reply=response;
                    runOnUiThread(()->{inFlight=false;if(reply!=null)showAck(reply);next();});
                });
            }
            public void onPreviewError(Exception error){runOnUiThread(()->{inFlight=false;if(!closing&&!paused)camera.postDelayed(()->next(),150);});}
        });
    }
    void showAck(String text){
        if(closing)return;
        status.setText(receiver.complete?"保存完了・読み戻し照合済み。PCが完了するまで保持してください。":
                "4色受付：確認済み "+receiver.received+" bytes / 今回 "+Integer.bitCount(receiver.mask)+"枚\n最大8枚をまとめて確認。戻りはACK・状態のみ。");
        if(text.equals(displayed))return;
        try{
            ack.setImageBitmap(new BarcodeEncoder().encodeBitmap(text,BarcodeFormat.QR_CODE,640,640));displayed=text;
        }catch(Exception e){status.setText("ACKを表示できません。保存完了は未確認です。");}
    }
    @Override protected void onResume(){super.onResume();paused=false;if(camera!=null&&checkSelfPermission("android.permission.CAMERA")==PackageManager.PERMISSION_GRANTED)camera.resume();}
    @Override protected void onPause(){paused=true;if(camera!=null)camera.pause();super.onPause();}
    @Override public void onRequestPermissionsResult(int r,String[] p,int[] g){super.onRequestPermissionsResult(r,p,g);if(r==81&&g.length>0&&g[0]==PackageManager.PERMISSION_GRANTED)camera.resume();}
    @Override protected void onDestroy(){closing=true;worker.execute(()->{try{if(receiver!=null)receiver.close();}catch(Exception ignored){}});worker.shutdown();super.onDestroy();}
}
