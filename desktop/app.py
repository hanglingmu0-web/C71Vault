"""Japanese desktop UI; all long operations run off the Tk event loop."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import sys
import tempfile
import threading
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from datetime import datetime
from vault_crypto import create_key,load_key,pack,restore
from vault_transport import MtpBridge
from vault_client import Client,default_state
from vault_recovery import escrow,recover
import hashlib

class App:
    def __init__(self,root):
        self.root=root;root.title('C71 Vault 0.3 — USB・光学バックアップ')
        root.geometry(f'{min(980,root.winfo_screenwidth()-80)}x{min(870,root.winfo_screenheight()-100)}')
        root.minsize(min(800,root.winfo_screenwidth()-80),min(650,root.winfo_screenheight()-100))
        self.events=queue.Queue();self.busy=False;self.buttons=[];self.archives=[]
        style=ttk.Style();style.theme_use('clam');style.configure('.',font=('Yu Gothic UI',10));style.configure('Title.TLabel',font=('Yu Gothic UI',23,'bold'));style.configure('TButton',padding=7)
        frame=ttk.Frame(root,padding=22);frame.pack(fill='both',expand=True)
        ttk.Label(frame,text='C71 Vault',style='Title.TLabel').pack(anchor='w')
        ttk.Label(frame,text='暗号化して保存。C71の端末認証で復元鍵を保管・回収します。').pack(anchor='w',pady=(0,12))
        self.state=tk.StringVar(value='未接続 — C71で「USB受付を開始」してください')
        ttk.Label(frame,textvariable=self.state,wraplength=840).pack(anchor='w')
        self.btn(frame,'端末を確認・初回登録',self.connect).pack(anchor='w',pady=8)
        cfg=ttk.LabelFrame(frame,text='バックアップ',padding=12);cfg.pack(fill='x',pady=8)
        preferences={}
        try:preferences=json.loads((default_state()/'ui.json').read_text(encoding='utf-8'))
        except (OSError,ValueError):pass
        self.source=tk.StringVar(value=preferences.get('source',''));self.key=tk.StringVar(value=preferences.get('key',''));self.label=tk.StringVar(value=preferences.get('label','文書バックアップ'))
        for row,title,var,cb in [(0,'対象フォルダ',self.source,self.choose_source),(1,'復元鍵ファイル',self.key,self.choose_key)]:
            ttk.Label(cfg,text=title).grid(row=row,column=0,sticky='w');ttk.Entry(cfg,textvariable=var).grid(row=row,column=1,sticky='ew',padx=8,pady=4);self.btn(cfg,'選択',cb).grid(row=row,column=2)
        cfg.columnconfigure(1,weight=1)
        ttk.Label(cfg,text='保存名').grid(row=2,column=0,sticky='w');ttk.Entry(cfg,textvariable=self.label).grid(row=2,column=1,sticky='ew',padx=8)
        self.btn(cfg,'復元鍵を新規作成',self.new_key).grid(row=3,column=0,pady=8)
        self.btn(cfg,'バックアップ開始',self.backup).grid(row=3,column=1,sticky='e',pady=8)
        self.btn(cfg,'復元鍵をC71に保管',self.escrow_key).grid(row=4,column=0,pady=6)
        self.btn(cfg,'光学でバックアップ',self.optical_backup).grid(row=4,column=1,sticky='e')
        ttk.Label(cfg,text='USB保存時は鍵の保管も確認します。初回のみC71で端末認証が必要です。',wraplength=800).grid(row=5,column=0,columnspan=3,sticky='w')
        box=ttk.LabelFrame(frame,text='C71の保存履歴',padding=8);box.pack(fill='both',expand=True,pady=8)
        self.tree=ttk.Treeview(box,columns=('date','name','size','key'),show='headings',height=6)
        for col,title,width in [('date','保存日時',155),('name','保存名',250),('size','サイズ',100),('key','復元鍵ID',160)]:self.tree.heading(col,text=title);self.tree.column(col,width=width)
        self.tree.pack(fill='both',expand=True)
        row=ttk.Frame(box);row.pack(fill='x',pady=5)
        self.btn(row,'履歴を更新',self.refresh).pack(side='left');self.btn(row,'選択した版を復元',self.restore_selected).pack(side='left',padx=8);self.btn(row,'手元の .c71b を復元',self.restore_local).pack(side='left')
        self.btn(row,'選択版の鍵をC71から回収',self.recover_key).pack(side='left',padx=6)
        self.logbox=tk.Text(frame,height=6,font=('Yu Gothic UI',9),state='disabled');self.logbox.pack(fill='x',pady=5)
        ttk.Label(frame,text='C71側の削除・初期化・故障への備えとして、元データと別のバックアップも保持してください。',wraplength=840).pack(anchor='w')
        root.after(100,self.pump)
        root.protocol('WM_DELETE_WINDOW',self.close)
    def close(self):
        if self.busy and not messagebox.askyesno('処理中です','閉じると保存結果を確認できなくなる場合があります。閉じますか？'):return
        self.root.destroy()
    def save_preferences(self):
        p=default_state();p.mkdir(parents=True,exist_ok=True)
        (p/'ui.json').write_text(json.dumps({'source':self.source.get(),'key':self.key.get(),'label':self.label.get()},ensure_ascii=False),encoding='utf-8')
    def btn(self,parent,text,fn):
        b=ttk.Button(parent,text=text,command=fn);self.buttons.append(b);return b
    def log(self,s):self.events.put(('log',str(s)))
    def pump(self):
        try:
            while True:
                kind,value=self.events.get_nowait()
                if kind=='log':self.logbox.configure(state='normal');self.logbox.insert('end',datetime.now().strftime('%H:%M:%S ')+value+'\n');self.logbox.see('end');self.logbox.configure(state='disabled')
                elif kind=='status':self.state.set(value)
                elif kind=='error':messagebox.showerror('処理を完了できませんでした',value);self.state.set('未完了 — ログを確認してください')
                elif kind=='done':
                    self.busy=False;[b.configure(state='normal') for b in self.buttons]
                    if hasattr(self,'progress'):self.progress.stop()
                elif kind=='archives':self.render_archives(value)
                elif kind=='confirm':
                    title,text,event,answer=value;answer.append(messagebox.askyesno(title,text));event.set()
                elif kind=='key':self.key.set(value)
                elif kind=='optical_frame':self.optical_frame(value)
                elif kind=='optical_status':
                    if hasattr(self,'optical_status'):self.optical_status.set(value)
        except queue.Empty:pass
        self.root.after(100,self.pump)
    def render_archives(self,value):
        self.tree.delete(*self.tree.get_children());self.archives=value
        for a in value:
            values=(datetime.fromtimestamp(a['stored_at']/1000).strftime('%Y/%m/%d %H:%M'),a['label'],f"{a['bytes']:,} bytes",a.get('key_id') or 'USBで取得',a.get('history_source','USB照合済み'))
            self.tree.insert('',0,iid=a['id'],values=values)
    def run(self,fn):
        if self.busy:return
        self.busy=True;[b.configure(state='disabled') for b in self.buttons]
        def work():
            try:fn()
            except Exception as e:self.log(type(e).__name__+': '+str(e));self.events.put(('error',str(e)))
            finally:self.events.put(('done',None))
        threading.Thread(target=work,daemon=True).start()
    def confirm(self,title,text):
        event=threading.Event();answer=[];self.events.put(('confirm',(title,text,event,answer)));event.wait();return answer[0]
    def client(self):
        c=Client(MtpBridge(),log=self.log);info,new=c.read_device()
        if new:
            if not self.confirm('C71の署名鍵を登録','C71画面の「端末の署名鍵」と次の値が一致しますか？\n\n'+info['fingerprint']):raise RuntimeError('端末の登録を取りやめました')
            c.trust_device()
        return c
    def connect(self):
        def task():
            c=self.client();c.pair();self.events.put(('status','接続確認済み — 端末の署名鍵を照合しました'));self.events.put(('archives',c.list()))
        self.run(task)
    def choose_source(self):
        p=filedialog.askdirectory(title='バックアップ対象フォルダ')
        if p:self.source.set(p)
    def choose_key(self):
        p=filedialog.askopenfilename(title='復元鍵を選択',filetypes=[('復元鍵','*.c71key'),('すべて','*.*')])
        if p:self.key.set(p)
    def new_key(self):
        p=filedialog.asksaveasfilename(title='復元鍵の保存先（バックアップ対象の外）',defaultextension='.c71key',initialfile='C71Vault-recovery.c71key')
        if p:
            try:create_key(p);self.key.set(p);messagebox.showinfo('復元鍵を作成しました','このファイルを別の安全な場所にも保管してください。USBバックアップ時にC71への鍵保管も確認します。光学転送前には「復元鍵をC71に保管」を実行してください。')
            except Exception as e:messagebox.showerror('鍵を作れませんでした',str(e))
    def backup(self):
        src=self.source.get();kp=self.key.get();label=self.label.get()
        self.save_preferences()
        def task():
            if not src or not kp:raise ValueError('対象フォルダと復元鍵を選んでください')
            if Path(kp).resolve().is_relative_to(Path(src).resolve()):raise ValueError('復元鍵をバックアップ対象フォルダの外に置いてください')
            key=load_key(kp);c=self.client();escrow(c,key)
            with tempfile.TemporaryDirectory(prefix='c71-backup-') as d:
                f=Path(d)/'data.c71b';meta=pack(src,f,key,self.log);result=c.backup(f,meta,label,self.series(src))
            self.events.put(('status',f"保存完了・C71で照合済み：{meta['file_count']}ファイル / {result['id']}"));self.events.put(('archives',c.list()))
        self.run(task)
    def refresh(self):self.run(lambda:self.events.put(('archives',self.client().list())))
    @staticmethod
    def series(source):return hashlib.sha256(os.path.normcase(str(Path(source).resolve())).encode('utf-8')).hexdigest()[:32]
    def escrow_key(self):
        keypath=self.key.get()
        def task():
            escrow(self.client(),load_key(keypath));self.events.put(('status','C71で復元鍵の保管・内容照合を確認しました'))
        self.run(task)
    def recover_key(self):
        selected=self.tree.selection()
        if not selected:messagebox.showinfo('保存履歴','鍵を回収する版を選択してください');return
        archive=next(a for a in self.archives if a['id']==selected[0]);id=archive['key_id']
        if not id:
            messagebox.showinfo('USBで履歴を取得','C71をPCへUSB接続し、C71でUSB受付を開始してから「履歴を更新」を押してください。鍵IDを取得してから回収できます。');return
        path=filedialog.asksaveasfilename(title='C71から回収する復元鍵の保存先',initialfile='C71-recovered-'+id+'.c71key',defaultextension='.c71key')
        if not path:return
        def task():
            recover(self.client(),id,path);self.events.put(('key',path));self.events.put(('status','復元鍵を回収しました。選択した版を復元できます'))
        self.run(task)
    def optical_frame(self,text):
        drawn=None
        if isinstance(text,tuple):text,drawn=text
        if not hasattr(self,'optical_window') or not self.optical_window.winfo_exists():return
        self.optical_image.show_text(text)
        self.optical_window.update_idletasks()
        if drawn is not None:drawn.set()
    def optical_backup(self):
        if self.busy:return
        src=self.source.get();kp=self.key.get();label=self.label.get();self.save_preferences()
        self.optical_window=tk.Toplevel(self.root);self.optical_window.title('C71 Vault 光学送信 — データはPCからのみ')
        self.optical_window.geometry(f'{min(850,self.root.winfo_screenwidth()-80)}x{min(900,self.root.winfo_screenheight()-120)}+30+30')
        self.optical_cancel=threading.Event();self.optical_status=tk.StringVar(value='C71は前面カメラをPC画面に向け、ACK画面をPCカメラに向けます。')
        ttk.Label(self.optical_window,textvariable=self.optical_status,wraplength=780).pack(pady=8)
        from vault_qr import ResponsiveQR
        self.optical_image=ResponsiveQR(self.optical_window);self.optical_image.pack(fill='both',expand=True)
        controls=ttk.Frame(self.optical_window);controls.pack(pady=12)
        mode=tk.StringVar(value='従来：白黒・512 bytes')
        selector=ttk.Combobox(controls,textvariable=mode,state='readonly',width=30,values=('従来：白黒・512 bytes','追加：4色・1,024 bytes・まとめACK'));selector.pack(side='left',padx=4)
        ttk.Label(controls,text='PCカメラ番号').pack(side='left');camera=tk.IntVar(value=0);ttk.Spinbox(controls,from_=0,to=9,textvariable=camera,width=3).pack(side='left')
        timing=ttk.Frame(self.optical_window);timing.pack(pady=(0,8))
        ttk.Label(timing,text='4色の1枚表示時間（秒）').pack(side='left');dwell=tk.DoubleVar(value=1.0)
        ttk.Spinbox(timing,from_=0.2,to=3,increment=0.1,textvariable=dwell,width=5).pack(side='left')
        ttk.Label(timing,text='C71でも同じ方式を選択。読取りが追いつかない場合は表示時間を増やします。').pack(side='left',padx=8)
        def close():self.optical_cancel.set();self.optical_window.destroy()
        self.optical_window.protocol('WM_DELETE_WINDOW',close)
        def start():
            try:index=camera.get();delay=dwell.get()
            except (ValueError,tk.TclError):messagebox.showerror('設定','カメラ番号と表示時間を数値で指定してください');return
            color=mode.get().startswith('追加');start_button.configure(state='disabled');selector.configure(state='disabled')
            def task():
                from vault_optical import send
                if color:
                    from vault_color import send
                if not src or not kp:raise ValueError('対象フォルダと復元鍵を選んでください')
                if Path(kp).resolve().is_relative_to(Path(src).resolve()):raise ValueError('復元鍵を対象フォルダの外に置いてください')
                with tempfile.TemporaryDirectory(prefix='c71-optical-') as d:
                    f=Path(d)/'data.c71b';meta=pack(src,f,load_key(kp),self.log)
                    def show(text):
                        if not color:self.events.put(('optical_frame',text));return
                        drawn=threading.Event();self.events.put(('optical_frame',(text,drawn)))
                        while not drawn.wait(0.05):
                            if self.optical_cancel.is_set():raise InterruptedError('光学送信を中止しました')
                    options={'dwell':delay} if color else {}
                    result=send(f,meta,label,self.series(src),show,lambda text:self.events.put(('optical_status',text)),self.optical_cancel,index,**options)
                self.events.put(('status','光学保存完了・C71で読み戻し照合済み：'+result['transfer']));self.events.put(('optical_status','保存完了・署名付き最終ACKを確認しました'))
            self.run(task)
        start_button=ttk.Button(controls,text='光学送信開始',command=start);start_button.pack(side='left',padx=12)
        ttk.Button(controls,text='中止・閉じる',command=close).pack(side='left')
    def restore_selected(self):
        selected=self.tree.selection()
        if not selected:messagebox.showinfo('保存履歴','復元する版を選択してください');return
        parent=filedialog.askdirectory(title='新しい復元フォルダを作る場所')
        if not parent:return
        id=selected[0];kp=self.key.get();dest=Path(parent)/('C71復元_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
        def task():
            key=load_key(kp);c=self.client()
            with tempfile.TemporaryDirectory(prefix='c71-download-') as d:
                p=Path(d)/'archive.c71b';c.download(id,p);result=restore(p,dest,key,self.log)
            self.events.put(('status',f"復元・全ファイル照合完了：{result['files']}ファイル → {dest}"))
        self.run(task)
    def restore_local(self):
        src=filedialog.askopenfilename(title='暗号化バックアップを選択',filetypes=[('バックアップ','*.c71b')])
        if not src:return
        parent=filedialog.askdirectory(title='新しい復元フォルダを作る場所')
        if not parent:return
        keyfile=self.key.get();dest=Path(parent)/('C71復元_'+datetime.now().strftime('%Y%m%d_%H%M%S'))
        def task():
            result=restore(src,dest,load_key(keyfile),self.log);self.events.put(('status',f"復元・全ファイル照合完了：{result['files']}ファイル → {dest}"))
        self.run(task)

if __name__=='__main__':
    from transfer_ui import TransferApp
    App=TransferApp
    root=tk.Tk()
    if len(sys.argv)==3 and sys.argv[1]=='--drop-self-test':
        from drop_diagnostics import run
        run(root,App(root),sys.argv[2])
    elif len(sys.argv)==3 and sys.argv[1] in ('--self-test','--self-test-mtp'):
        from runtime_diagnostics import run
        root.withdraw()
        sys.exit(run(root,App(root),sys.argv[2],check_mtp=sys.argv[1]=='--self-test-mtp'))
    else:
        App(root);root.mainloop()
