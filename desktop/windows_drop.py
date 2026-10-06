"""Explorer file drops through WM_DROPFILES; no shell execution or extra runtime."""
import ctypes
import queue
import sys
from ctypes import wintypes as w

class FileDrop:
    def __init__(self,root,callback):
        self.root=root;self.callback=callback
        self.pending=queue.SimpleQueue()
        self.closed=False
        self.poll_id=None
        u=ctypes.WinDLL('user32',use_last_error=True);s=ctypes.WinDLL('shell32',use_last_error=True)
        self.u=u;self.s=s
        self.proc_type=ctypes.WINFUNCTYPE(ctypes.c_ssize_t,w.HWND,w.UINT,w.WPARAM,w.LPARAM)
        u.GetAncestor.argtypes=[w.HWND,w.UINT];u.GetAncestor.restype=w.HWND
        u.SetWindowLongPtrW.argtypes=[w.HWND,ctypes.c_int,ctypes.c_void_p];u.SetWindowLongPtrW.restype=ctypes.c_void_p
        u.CallWindowProcW.argtypes=[ctypes.c_void_p,w.HWND,w.UINT,w.WPARAM,w.LPARAM];u.CallWindowProcW.restype=ctypes.c_ssize_t
        s.DragAcceptFiles.argtypes=[w.HWND,w.BOOL];s.DragFinish.argtypes=[w.HANDLE]
        s.DragQueryFileW.argtypes=[w.HANDLE,w.UINT,w.LPWSTR,w.UINT];s.DragQueryFileW.restype=w.UINT
        root.update_idletasks();self.hwnd=u.GetAncestor(root.winfo_id(),2)
        def proc(hwnd,msg,wp,lp):
            if msg==0x233:
                try:
                    paths=[]
                    for i in range(s.DragQueryFileW(wp,0xffffffff,None,0)):
                        n=s.DragQueryFileW(wp,i,None,0);b=ctypes.create_unicode_buffer(n+1)
                        s.DragQueryFileW(wp,i,b,n+1);paths.append(b.value)
                    # A native WNDPROC can run while Tcl has released Python's
                    # thread state. Even root.after_idle() here can abort Python.
                    # Only collect data; a normal Tk timer delivers it to the UI.
                    if not self.closed:self.pending.put((paths,None))
                except Exception:
                    self.pending.put((None,sys.exc_info()))
                finally:s.DragFinish(wp)
                return 0
            return u.CallWindowProcW(self.old,hwnd,msg,wp,lp)
        self.proc=self.proc_type(proc)
        self.old=u.SetWindowLongPtrW(self.hwnd,-4,ctypes.cast(self.proc,ctypes.c_void_p))
        if not self.old:raise ctypes.WinError(ctypes.get_last_error())
        s.DragAcceptFiles(self.hwnd,True)
        self.poll_id=root.after(50,self._poll)

    def _poll(self):
        self.poll_id=None
        if self.closed:return
        try:
            # Bound each batch so repeated drops cannot starve the UI.
            for _ in range(32):
                try:paths,error=self.pending.get_nowait()
                except queue.Empty:break
                if error:self.root.report_callback_exception(*error)
                else:self.callback(paths)
                if self.closed:break
        finally:
            if not self.closed:self.poll_id=self.root.after(50,self._poll)

    def close(self):
        if self.closed:return
        self.closed=True
        if self.poll_id is not None:
            self.root.after_cancel(self.poll_id)
            self.poll_id=None
        self.s.DragAcceptFiles(self.hwnd,False)
        self.u.SetWindowLongPtrW(self.hwnd,-4,self.old)
        while not self.pending.empty():self.pending.get_nowait()
