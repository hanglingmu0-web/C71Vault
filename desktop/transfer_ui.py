"""Unified selection and transport UI; legacy recovery tools remain available."""
import hashlib,json,os,queue,tempfile,threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from app import App as LegacyApp
from vault_client import default_state
from vault_crypto import pack,load_key,selection_entries
from vault_recovery import escrow
from vault_history import load_history,remember_transfer

class TransferApp(LegacyApp):
    def __init__(self,root):
        self.root=root;self.events=queue.Queue();self.busy=False;self.buttons=[];self.archives=[];self.sources=[]
        self.source=tk.StringVar();self.cancel=threading.Event()
        root.title('C71 Vault 0.5.3 — バックアップ転送')
        root.geometry('980x820');root.minsize(800,680)
        style=ttk.Style();style.theme_use('clam');style.configure('.',font=('Yu Gothic UI',10));style.configure('TButton',padding=6)
        outer=ttk.Frame(root,padding=18);outer.pack(fill='both',expand=True)
        ttk.Label(outer,text='C71 Vault',font=('Yu Gothic UI',24,'bold')).pack(anchor='w')
        self.state=tk.StringVar(value='ファイルを追加し、C71で保存フォルダと受信方式を選んでください。')
        ttk.Label(outer,textvariable=self.state,wraplength=900).pack(anchor='w',pady=8)
        tabs=ttk.Notebook(outer);tabs.pack(fill='both',expand=True)
        page=ttk.Frame(tabs,padding=14);tools=ttk.Frame(tabs,padding=14)
        tabs.add(page,text='転送');tabs.add(tools,text='保存履歴・復元・鍵・USB初回登録')
        self.key=tk.StringVar();self.label=tk.StringVar(value='文書バックアップ')
        try:
            prefs=json.loads((default_state()/'ui.json').read_text(encoding='utf-8'));self.key.set(prefs.get('key',''));self.label.set(prefs.get('label','文書バックアップ'))
        except (OSError,ValueError):pass
        ttk.Label(page,text='1  ファイル・フォルダを追加',font=('Yu Gothic UI',13,'bold')).pack(anchor='w')
        ttk.Label(page,text='Word・画像・テキストなどを、このウィンドウへドラッグ＆ドロップできます。').pack(anchor='w',pady=4)
        self.files=tk.Listbox(page,height=6,selectmode='extended',font=('Yu Gothic UI',10));self.files.pack(fill='both',expand=True)
        row=ttk.Frame(page);row.pack(fill='x',pady=6)
        for text,fn in [('ファイルを追加',self.choose_files),('フォルダを追加',self.choose_source),('選択を外す',self.remove_sources),('すべて外す',self.clear_sources)]:self.btn(row,text,fn).pack(side='left',padx=(0,6))
        cfg=ttk.Frame(page);cfg.pack(fill='x');cfg.columnconfigure(1,weight=1)
        for n,title,var in [(0,'保存名',self.label),(1,'復元鍵',self.key)]:
            ttk.Label(cfg,text=title).grid(row=n,column=0,sticky='w');ttk.Entry(cfg,textvariable=var).grid(row=n,column=1,sticky='ew',padx=8,pady=3)
        self.btn(cfg,'鍵を選択',self.choose_key).grid(row=1,column=2)
        ttk.Label(page,text='2  転送方法を選択',font=('Yu Gothic UI',13,'bold')).pack(anchor='w',pady=(12,4))
        self.transport=tk.StringVar(value='USB');row=ttk.Frame(page);row.pack(fill='x')
        for name in ('USB','2次元コード','MIDI'):
            ttk.Radiobutton(row,text=name,variable=self.transport,value=name,command=self.transport_changed).pack(side='left',padx=(0,25))
        self.options=ttk.Frame(page);self.options.pack(fill='x',pady=7)
        self.optical_mode=tk.StringVar(value='白黒');self.camera=tk.StringVar(value='0');self.dwell=tk.StringVar(value='1.0');self.com=tk.StringVar()
        self.optical_options=ttk.Frame(self.options)
        ttk.Combobox(self.optical_options,textvariable=self.optical_mode,values=('白黒','4色'),state='readonly',width=8).pack(side='left')
        for title,var in [('PCカメラ',self.camera),('4色表示秒',self.dwell)]:
            ttk.Label(self.optical_options,text=title).pack(side='left',padx=7);ttk.Entry(self.optical_options,textvariable=var,width=5).pack(side='left')
        self.midi_options=ttk.Frame(self.options)
        ttk.Label(self.midi_options,text='送信側Arduinoのポート').pack(side='left')
        self.port_box=ttk.Combobox(self.midi_options,textvariable=self.com,width=14,state='readonly');self.port_box.pack(side='left',padx=8)
        self.btn(self.midi_options,'再検索',self.scan_ports).pack(side='left')
        self.hint=tk.StringVar();ttk.Label(page,textvariable=self.hint,wraplength=850).pack(anchor='w',pady=4)
        row=ttk.Frame(page);row.pack(fill='x',pady=10)
        self.btn(row,'転送開始',self.start_transfer).pack(side='left');ttk.Button(row,text='転送を中止',command=self.cancel_transfer).pack(side='left',padx=8)
        self.progress=ttk.Progressbar(row,mode='indeterminate');self.progress.pack(side='left',fill='x',expand=True,padx=8)
        row=ttk.Frame(tools);row.pack(fill='x')
        for text,fn in [('端末を確認・初回登録',self.connect),('復元鍵を新規作成',self.new_key),('復元鍵をC71に保管',self.escrow_key)]:self.btn(row,text,fn).pack(side='left',padx=3)
        ttk.Label(tools,text='復元・最新の履歴取得：C71をR4から外してPCへUSB接続 → ファイル転送を有効 → 通常版C71 VaultでUSB受信開始 →「履歴を更新」。MIDIの戻り経路はACK専用です。',wraplength=850).pack(anchor='w',pady=8)
        ttk.Label(tools,text='PCに残る保存完了記録と前回USB照合時点の履歴を表示します。現在のC71の状態は「履歴を更新」で確認してください。MIDI未照合行の日時はPCでのACK記録日時です。',wraplength=850).pack(anchor='w',pady=4)
        keyrow=ttk.Frame(tools);keyrow.pack(fill='x',pady=4)
        ttk.Label(keyrow,text='復元鍵').pack(side='left');ttk.Entry(keyrow,textvariable=self.key).pack(side='left',fill='x',expand=True,padx=8);self.btn(keyrow,'鍵を選択',self.choose_key).pack(side='left')
        self.tree=ttk.Treeview(tools,columns=('date','name','size','key','source'),show='headings',height=8)
        for col,title,width in [('date','保存／ACK記録日時',140),('name','保存名',170),('size','サイズ',95),('key','復元鍵ID',145),('source','確認状態',210)]:self.tree.heading(col,text=title);self.tree.column(col,width=width)
        self.tree.pack(fill='both',expand=True)
        for text,fn in [('履歴を更新',self.refresh),('選択した版を復元',self.restore_selected),('手元の .c71b を復元',self.restore_local),('選択版の鍵をC71から回収',self.recover_key)]:self.btn(tools,text,fn).pack(anchor='w',pady=2)
        self.logbox=tk.Text(outer,height=5,state='disabled',font=('Yu Gothic UI',9));self.logbox.pack(fill='x',pady=(10,0))
        self.drop=None
        if os.name=='nt':
            from windows_drop import FileDrop
            self.drop=FileDrop(root,self.add_sources)
        root.after(100,self.pump);root.protocol('WM_DELETE_WINDOW',self.close)
        self.transport_changed()
        self.reload_history()
    def reload_history(self):
        try:self.events.put(('archives',load_history(default_state(),self.log)));return True
        except Exception as error:self.log('PCの保存記録を読み込めません: '+str(error));return False
    def save_preferences(self):
        p=default_state();p.mkdir(parents=True,exist_ok=True)
        (p/'ui.json').write_text(json.dumps({'key':self.key.get(),'label':self.label.get()},ensure_ascii=False),encoding='utf-8')
    def choose_files(self):self.add_sources(filedialog.askopenfilenames(title='バックアップするファイル'))
    def choose_source(self):
        p=filedialog.askdirectory(title='バックアップするフォルダ')
        if p:self.add_sources([p])
    def add_sources(self,paths):
        if self.busy:return
        for p in paths:
            p=str(Path(p).absolute())
            if p not in self.sources:self.sources.append(p)
        self.render_sources()
    def remove_sources(self):
        for i in reversed(self.files.curselection()):del self.sources[i]
        self.render_sources()
    def clear_sources(self):self.sources=[];self.render_sources()
    def render_sources(self):
        self.files.delete(0,'end')
        for p in self.sources:self.files.insert('end',p)
        self.state.set(f'{len(self.sources)}項目を選択 — 受信側の準備後に「転送開始」')
    def scan_ports(self):
        from serial.tools import list_ports
        ports=list(list_ports.comports());values=[p.device for p in ports];self.port_box.configure(values=values)
        if self.com.get() not in values:self.com.set(values[0] if values else '')
    def transport_changed(self):
        self.optical_options.pack_forget();self.midi_options.pack_forget()
        mode=self.transport.get()
        if mode=='2次元コード':self.optical_options.pack(anchor='w');self.hint.set('C71でも白黒／4色を合わせて受信開始。暗号化後16MiBまで。初回登録・鍵保管は事前にUSBで行います。')
        elif mode=='MIDI':self.midi_options.pack(anchor='w');self.scan_ports();self.hint.set('PC→R3→フォトカプラ→R4→C71。ACK用の戻り経路も必要です。暗号化後16MiBまで。')
        else:self.hint.set('C71でUSB受信を開始してください。暗号化後8GiBまで。保存・読み戻し完了の署名付き応答を確認します。')
    def cancel_transfer(self):
        if self.busy:
            self.cancel.set();self.log('中止を要求しました。C71で処理済みの保存データは削除しません。')
    def start_transfer(self):
        if self.busy:return
        try:
            sources=list(self.sources);kp=self.key.get();label=self.label.get().strip();mode=self.transport.get()
            if not sources:raise ValueError('ファイルまたはフォルダを追加してください')
            if not kp:raise ValueError('復元鍵を選択してください。「復元・鍵・USB初回登録」から作成できます')
            if not label or len(label)>100 or any(ord(c)<32 for c in label):raise ValueError('保存名は1～100文字で指定してください')
            if any(Path(kp).resolve().is_relative_to(Path(p).resolve()) for p in sources):raise ValueError('復元鍵をバックアップ対象から外してください')
            index=int(self.camera.get());delay=float(self.dwell.get());color=self.optical_mode.get()=='4色';port=self.com.get()
            if mode=='MIDI' and not port:raise ValueError('ArduinoのCOMポートを選択してください')
            if mode=='2次元コード' and (index<0 or not .2<=delay<=3):raise ValueError('カメラ番号は0以上、表示時間は0.2～3秒です')
            key=load_key(kp)
        except Exception as e:messagebox.showerror('転送の準備',str(e));return
        self.save_preferences();self.cancel=threading.Event();self.optical_cancel=self.cancel
        if mode=='2次元コード':
            from vault_qr import ResponsiveQR
            self.optical_window=tk.Toplevel(self.root);self.optical_window.title('C71 Vault — 2次元コード転送')
            self.optical_window.geometry(f'800x{min(850,self.root.winfo_screenheight()-100)}')
            self.optical_status=tk.StringVar(value='暗号化を準備しています')
            ttk.Label(self.optical_window,textvariable=self.optical_status,wraplength=750).pack(pady=8)
            self.optical_image=ResponsiveQR(self.optical_window);self.optical_image.pack(fill='both',expand=True)
            def close():self.cancel.set();self.optical_window.destroy()
            ttk.Button(self.optical_window,text='中止・閉じる',command=close).pack(pady=8);self.optical_window.protocol('WM_DELETE_WINDOW',close)
        self.progress.start(12)
        def task():
            try:
                roots,_,_=selection_entries(sources)
                series=hashlib.sha256('\n'.join(sorted(os.path.normcase(str(p)) for p in roots)).encode()).hexdigest()[:32]
                def progress(s):
                    if self.cancel.is_set():raise InterruptedError('中止しました。保存完了は確認していません')
                    self.log(s);self.events.put(('status',s))
                c=None
                if mode=='USB':c=self.client();c.cancel=self.cancel;escrow(c,key)
                else:
                    from vault_optical import pinned_client
                    pinned_client()
                with tempfile.TemporaryDirectory(prefix='c71-transfer-') as d:
                    archive=Path(d)/'data.c71b';meta=pack(sources,archive,key,progress)
                    progress(f"暗号化完了：{meta['file_count']}ファイル / {meta['bytes']:,} bytes — {mode}転送")
                    if mode=='USB':result=c.backup(archive,meta,label,series)
                    elif mode=='MIDI':
                        from midi_transfer import send
                        result=send(archive,series,port,progress,self.cancel,label=label)
                    else:
                        from vault_optical import send
                        if color:
                            from vault_color import send
                        def show(frame):
                            drawn=threading.Event();self.events.put(('optical_frame',(frame,drawn)))
                            while not drawn.wait(.05):
                                if self.cancel.is_set():raise InterruptedError('中止しました')
                        result=send(archive,meta,label,series,show,lambda s:(self.events.put(('optical_status',s)),self.events.put(('status',s))),self.cancel,index,**({'dwell':delay} if color else {}))
                if mode=='MIDI':
                    try:remember_transfer(default_state(),result['session'],meta,label)
                    except OSError as error:self.log('保存完了。PC側の表示情報保存に失敗: '+str(error))
                if mode=='USB':
                    try:self.events.put(('archives',c.list()))
                    except Exception as error:self.log('バックアップは保存済みです。一覧の更新だけ失敗しました: '+str(error))
                else:self.reload_history()
                self.events.put(('status',f"保存完了・C71の読み戻し検証済み：{meta['file_count']}ファイル"+('。保存履歴タブを確認してください。復元はC71をPCへUSB接続してください。' if mode=='MIDI' else '')))
                self.events.put(('optical_status','保存完了・署名付きACKを確認しました'))
                self.log('C71の保存完了応答を検証しました。')
            finally:self.events.put(('log','転送処理が終了しました。'))
        self.run(task)
    def close(self):
        if self.busy:
            messagebox.showinfo('転送中','中止ボタンを押し、処理が終了してから閉じてください。');return
        if self.drop:self.drop.close()
        self.root.destroy()

if __name__=='__main__':
    root=tk.Tk();TransferApp(root);root.mainloop()
