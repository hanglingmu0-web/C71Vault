package jp.c71.vault;

import android.app.*;
import android.content.*;
import android.hardware.usb.*;
import android.media.midi.*;
import android.os.*;
import android.view.*;
import android.widget.*;
import com.hoho.android.usbserial.driver.*;
import java.io.*;
import java.util.*;

public class IsolatedSerialActivity extends Activity {
    public static final int DEFAULT_BAUD=115200;
    static final String PERMISSION="jp.c71.vault.SERIAL_USB_PERMISSION";
    UsbManager manager;MidiManager midi;Spinner devices,baud;TextView details;Button start,stop,scan;
    final List<Choice> choices=new ArrayList<>();
    volatile boolean stopping=true;volatile Closeable debugInput;volatile UsbSerialPort port;
    volatile UsbDeviceConnection connection;volatile Thread worker;
    volatile MidiDevice midiDevice;volatile MidiOutputPort midiPort;volatile MidiInputPort midiReply;
    IsolatedReceiver receiver;Vault vault;Choice pending,selected;boolean destroyed;long lastUi;
    String connectionState="未接続",loggedReceipt="";int speed=DEFAULT_BAUD;
    final MidiManager.DeviceCallback midiEvents=new MidiManager.DeviceCallback(){
        @Override public void onDeviceRemoved(MidiDeviceInfo info){if(selected!=null&&selected.midiInfo!=null&&selected.midiInfo.getId()==info.getId())stopReceiving("USB MIDI切断");}
    };
    static final class Choice {
        final UsbDevice device;final UsbSerialDriver driver;final int index;final String label;MidiDeviceInfo midiInfo;
        Choice(UsbDevice device,UsbSerialDriver driver,int index,String label){this.device=device;this.driver=driver;this.index=index;this.label=label;}
        public String toString(){return label;}
    }
    public interface DebugPipe extends Closeable {InputStream open()throws Exception;void status(String json)throws Exception;}
    final BroadcastReceiver events=new BroadcastReceiver(){public void onReceive(Context c,Intent intent){
        UsbDevice device=intent.getParcelableExtra(UsbManager.EXTRA_DEVICE);
        if(PERMISSION.equals(intent.getAction())){
            Choice requested=pending;pending=null;
            if(requested==null||device==null||!device.equals(requested.device))return;
            if(intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED,false)&&manager.hasPermission(device))connect(requested);
            else {connectionState="USB接続許可なし";render();}
        }else if(UsbManager.ACTION_USB_DEVICE_DETACHED.equals(intent.getAction())&&selected!=null&&device!=null&&device.equals(selected.device))stopReceiving("USB切断");
    }};
    @android.annotation.SuppressLint("UnspecifiedRegisterReceiverFlag")
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);stopService(new Intent(this,VaultService.class));manager=getSystemService(UsbManager.class);
        try{vault=Vault.get(this);}catch(Exception e){new AlertDialog.Builder(this).setMessage("保管領域を開けません: "+e.getMessage()).setPositiveButton("閉じる",(d,w)->finish()).show();return;}
        midi=getSystemService(MidiManager.class);if(midi!=null)midi.registerDeviceCallback(midiEvents,new Handler(getMainLooper()));getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        ScrollView sc=new ScrollView(this);LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);body.setPadding(24,60,24,70);sc.addView(body);setContentView(sc);
        TextView title=new TextView(this);title.setText("MIDI/絶縁通信受付"+(BuildConfig.DEBUG?"（開発版）":""));title.setTextSize(24);body.addView(title);
        TextView note=new TextView(this);note.setText("MIDI 1.0 SysEx受信：7-bit符号化・CRC・SHA-256を検証します。診断データは保存せず、登録済みPCが署名したバックアップだけを保管します。\nUSB MIDIまたはUSBシリアル経由。絶縁にはArduino間のフォトカプラ配線が必要です。");body.addView(note);
        devices=new Spinner(this);body.addView(devices);baud=new Spinner(this);baud.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,new String[]{"115200","9600","31250"}));body.addView(baud);
        scan=new Button(this);scan.setText("接続デバイスを再検索");scan.setOnClickListener(v->scan());body.addView(scan);
        start=new Button(this);start.setText("受信開始");start.setOnClickListener(v->requestStart());body.addView(start);
        stop=new Button(this);stop.setText("受信停止");stop.setOnClickListener(v->stopReceiving("手動停止"));body.addView(stop);
        details=new TextView(this);details.setTextSize(16);details.setTextIsSelectable(true);body.addView(details);
        Button close=new Button(this);close.setText("受付画面を閉じる");close.setOnClickListener(v->finish());body.addView(close);
        IntentFilter filter=new IntentFilter(PERMISSION);filter.addAction(UsbManager.ACTION_USB_DEVICE_DETACHED);
        if(Build.VERSION.SDK_INT>=33)registerReceiver(events,filter,Context.RECEIVER_NOT_EXPORTED);else registerReceiver(events,filter);
        scan();
        if(getIntent().getBooleanExtra("auto_start",false)&&choices.size()==1&&choices.get(0).driver!=null)new Handler(getMainLooper()).post(this::requestStart);
    }
    void scan(){
        if(worker!=null||pending!=null)return;choices.clear();
        List<UsbDevice> list=new ArrayList<>(manager.getDeviceList().values());list.sort(Comparator.comparing(UsbDevice::getDeviceName));
        for(UsbDevice device:list){
            UsbSerialDriver driver=UsbSerialProber.getDefaultProber().probeDevice(device);
            String label=String.format(Locale.ROOT,"%s [%04X:%04X]",device.getProductName()==null?device.getDeviceName():device.getProductName(),device.getVendorId(),device.getProductId());
            if(driver==null)choices.add(new Choice(device,null,0,label+"（未対応）"));
            else for(int p=0;p<driver.getPorts().size();p++)choices.add(new Choice(device,driver,p,label+" / "+driver.getClass().getSimpleName()+" #"+p));
        }
        if(midi!=null)for(MidiDeviceInfo info:midi.getDevices())if(info.getType()==MidiDeviceInfo.TYPE_USB){
            for(MidiDeviceInfo.PortInfo port:info.getPorts())if(port.getType()==MidiDeviceInfo.PortInfo.TYPE_OUTPUT){
                Choice c=new Choice(null,null,port.getPortNumber(),"USB MIDI："+info.getProperties().getString(MidiDeviceInfo.PROPERTY_NAME,"MIDI device")+" #"+port.getPortNumber());c.midiInfo=info;choices.add(c);
            }
        }
        if(BuildConfig.DEBUG)choices.add(new Choice(null,null,0,"開発限定：PC/ADB中継（USB Host直結ではありません）"));
        devices.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,choices));
        connectionState=list.isEmpty()?"USB Host機器なし。直結時はOTGで接続して再検索してください。":"接続候補 "+list.size()+"台";render();
    }
    void requestStart(){
        if(worker!=null||pending!=null)return;
        Choice choice=(Choice)devices.getSelectedItem();if(choice==null){connectionState="機器を選択してください";render();return;}
        speed=Integer.parseInt(baud.getSelectedItem().toString());
        if(choice.device==null){connect(choice);return;}
        if(choice.driver==null){connectionState="このUSB機器に対応するシリアルドライバがありません";render();return;}
        if(manager.hasPermission(choice.device)){connect(choice);return;}
        pending=choice;connectionState="USB接続許可を待っています";render();
        PendingIntent permission=PendingIntent.getBroadcast(this,0,new Intent(PERMISSION).setPackage(getPackageName()),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_MUTABLE);
        manager.requestPermission(choice.device,permission);
    }
    void connect(Choice choice){
        if(destroyed||worker!=null)return;selected=choice;stopping=false;connectionState="接続中";
        loggedReceipt="";receiver=new IsolatedReceiver(s->{
            if(s.complete&&!s.sha256.equals(loggedReceipt)){loggedReceipt=s.sha256;android.util.Log.i("C71Midi","verified device="+choice.label+" bytes="+s.received+" sequence="+s.sequence+" crc_frames="+s.crcFrames+" errors="+s.errors+" sha256="+s.sha256+" committed="+s.committed);}
            long now=SystemClock.elapsedRealtime();if(now-lastUi>150||s.complete||!s.lastError.equals("なし")){lastUi=now;runOnUiThread(this::render);}
        },vault);
        receiver.reply=(frame,ok)->{
            try{byte[] reply=MidiReceipt.encode(vault,frame,receiver,ok);
                if(port!=null)port.write(reply,3000);
                else if(midiReply!=null)midiReply.send(reply,0,reply.length);
            }catch(Exception e){connectionState="ACK送信失敗："+e.getMessage();runOnUiThread(this::render);}
        };
        worker=new Thread(()->{
            try{
                if(choice.midiInfo!=null){
                    java.util.concurrent.CountDownLatch opened=new java.util.concurrent.CountDownLatch(1);
                    midi.openDevice(choice.midiInfo,device->{if(stopping){try{if(device!=null)device.close();}catch(Exception ignored){}}else midiDevice=device;opened.countDown();},new Handler(getMainLooper()));
                    if(!opened.await(10,java.util.concurrent.TimeUnit.SECONDS)||midiDevice==null)throw new IOException("USB MIDI open failed");
                    if(choice.index<choice.midiInfo.getInputPortCount())midiReply=midiDevice.openInputPort(choice.index);
                    midiPort=midiDevice.openOutputPort(choice.index);if(midiPort==null)throw new IOException("MIDI output port unavailable");
                    midiPort.connect(new MidiReceiver(){public void onSend(byte[] b,int offset,int count,long timestamp){if(!stopping)receiver.feed(Arrays.copyOfRange(b,offset,offset+count),count);}});
                    runOnUiThread(()->{connectionState="USB MIDI SysEx受信中（USBにbaud設定はありません）";render();});
                    while(!stopping)Thread.sleep(200);
                }else if(choice.device==null){
                    if(!BuildConfig.DEBUG)throw new IOException("debug transport disabled");
                    DebugPipe pipe=(DebugPipe)Class.forName("jp.c71.vault.DevelopmentSerialPipe").getDeclaredConstructor().newInstance();debugInput=pipe;
                    runOnUiThread(()->{connectionState="開発用中継待ち（非絶縁）";render();});
                    InputStream input=pipe.open();byte[] bytes=new byte[2048];int n;
                    while(!stopping&&(n=input.read(bytes))!=-1){receiver.feed(bytes,n);pipe.status(statusJson());}
                }else{
                    connection=manager.openDevice(choice.device);if(connection==null)throw new IOException("USB open failed");
                    port=choice.driver.getPorts().get(choice.index);port.open(connection);port.setParameters(speed,8,UsbSerialPort.STOPBITS_1,UsbSerialPort.PARITY_NONE);port.setDTR(true);
                    runOnUiThread(()->{connectionState="USBシリアル接続・受信中";render();});
                    byte[] bytes=new byte[2048];while(!stopping){int n=port.read(bytes,250);if(n>0)receiver.feed(bytes,n);}
                }
            }catch(Exception e){if(!stopping)receiver.error("接続: "+e.getMessage());}
            finally{closeHandles();receiver.close();runOnUiThread(()->{worker=null;stopping=true;connectionState="停止";render();});}
        },"C71 isolated serial");worker.start();render();
    }
    String statusJson()throws Exception {
        synchronized(receiver){return new org.json.JSONObject().put("bytes",receiver.received).put("sequence",receiver.sequence).put("complete",receiver.complete).put("committed",receiver.committed).put("crc_frames",receiver.crcFrames).put("errors",receiver.errors).put("sha256",receiver.sha256).put("error",receiver.lastError).toString();}
    }
    void closeHandles(){try{if(midiReply!=null)midiReply.close();}catch(Exception ignored){}midiReply=null;try{if(debugInput!=null)debugInput.close();}catch(Exception ignored){}try{if(port!=null)port.close();}catch(Exception ignored){}try{if(connection!=null)connection.close();}catch(Exception ignored){}try{if(midiPort!=null)midiPort.close();}catch(Exception ignored){}try{if(midiDevice!=null)midiDevice.close();}catch(Exception ignored){}debugInput=null;port=null;connection=null;midiPort=null;midiDevice=null;}
    void stopReceiving(String reason){pending=null;stopping=true;connectionState=reason;closeHandles();render();}
    void render(){
        if(destroyed||details==null)return;boolean busy=worker!=null||pending!=null;
        start.setEnabled(!busy);scan.setEnabled(!busy);devices.setEnabled(!busy);baud.setEnabled(!busy);stop.setEnabled(busy);
        String text="接続デバイス："+(selected==null?"未選択":selected.label)+"\n接続状態："+connectionState+"\n通信速度："+speed+" baud / 8N1\n";
        if(receiver==null)text+="受信バイト数：0\n現在のフレーム番号：—\nCRC/検証結果：未受信\n最後のエラー：なし";
        else synchronized(receiver){text+="受信バイト数："+receiver.received+" / "+receiver.expected+"（回線 "+receiver.wireBytes+"）\n現在のフレーム番号："+receiver.sequence+"\nCRC一致フレーム："+receiver.crcFrames+"\nCRC/検証結果："+receiver.state+"\nSHA-256："+receiver.sha256+"\n期待SHA-256："+receiver.expectedHash+"\n最後のエラー："+receiver.lastError+"\nエラー数："+receiver.errors;}
        details.setText(text);
    }
    @Override protected void onStop(){super.onStop();stopReceiving("画面を離れたため停止");}
    @Override protected void onDestroy(){destroyed=true;stopReceiving("終了");try{unregisterReceiver(events);}catch(IllegalArgumentException ignored){}if(midi!=null)midi.unregisterDeviceCallback(midiEvents);super.onDestroy();}
}
