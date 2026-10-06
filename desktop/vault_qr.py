"""Integer-scaled QR display which always includes its full quiet zone."""
import tkinter as tk
import qrcode
from PIL import ImageTk

def render_qr(text,width,height):
    from vault_color import ColorFrame, render_color
    if isinstance(text,ColorFrame):return render_color(text,width,height)
    qr=qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M,box_size=1,border=4)
    qr.add_data(text);qr.make(fit=True)
    modules=qr.modules_count+8
    scale=min(int(width),int(height))//modules
    if scale<1:raise ValueError('QR全体を表示できるまでウィンドウを拡大してください')
    qr.box_size=scale
    return qr.make_image().convert('RGB')

class ResponsiveQR(tk.Canvas):
    def __init__(self,parent,**kwargs):
        super().__init__(parent,background='white',highlightthickness=0,**kwargs)
        self.text='';self.photo=None;self.bind('<Configure>',lambda event:self.redraw())
    def show_text(self,text):self.text=text;self.redraw()
    def redraw(self):
        if not self.text or self.winfo_width()<20 or self.winfo_height()<20:return
        self.delete('all')
        try:
            image=render_qr(self.text,self.winfo_width()-16,self.winfo_height()-16)
            self.photo=ImageTk.PhotoImage(image)
            self.create_image(self.winfo_width()//2,self.winfo_height()//2,image=self.photo)
        except ValueError as e:self.create_text(10,10,anchor='nw',text=str(e),width=max(20,self.winfo_width()-20))
