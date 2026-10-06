import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
import base64, hashlib, struct
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from PIL import Image, ImageEnhance, ImageFilter
from vault_color import *


def client():
    private=ec.generate_private_key(ec.SECP256R1())
    return SimpleNamespace(private=private,client_id='a'*64,device_key=private.public_key())


@pytest.mark.parametrize('transform',['plain','dim','warm','blur','perspective','rotate'])
def test_binary_four_color_roundtrip_under_image_transforms(transform):
    c=client();raw=packet(c,'b'*32,'c'*32,DATA,5,bytes(range(256))*4)
    image=render_color(ColorFrame(raw),700,700)
    assert len(image.getcolors())==4
    if transform=='dim':image=ImageEnhance.Brightness(image).enhance(0.60)
    elif transform=='warm':
        r,g,b=image.split();image=Image.merge('RGB',(r,g.point(lambda v:int(v*.85)),b.point(lambda v:int(v*.65))))
    elif transform=='blur':image=image.filter(ImageFilter.GaussianBlur(.65))
    elif transform=='perspective':
        import numpy as np,cv2
        w,h=image.size
        matrix=cv2.getPerspectiveTransform(np.float32([[0,0],[w-1,0],[w-1,h-1],[0,h-1]]),
                                          np.float32([[25,10],[w-40,30],[w-10,h-25],[5,h-5]]))
        image=Image.fromarray(cv2.warpPerspective(np.array(image),matrix,(w,h),borderValue=(255,255,255)))
    elif transform=='rotate':image=image.rotate(90)
    decoded=decode_color_image(image)
    assert decoded==raw
    assert unpack_packet(decoded,c.private.public_key())['body']==bytes(range(256))*4


def test_layers_cannot_be_spliced_from_different_frames():
    c=client();a=packet(c,'b'*32,'c'*32,DATA,1,b'a'*1024);b=packet(c,'b'*32,'c'*32,DATA,2,b'b'*1024)
    with pytest.raises(ValueError):join_layers(layers(a)[0],layers(b)[1])
    with pytest.raises(ValueError):join_layers(layers(a)[0],layers(a)[0])
    with pytest.raises(ValueError):join_layers(layers(a)[0][:-1],layers(a)[1])


@pytest.mark.parametrize('mutation',['data','client','signature','length','trailing','unknown-op'])
def test_binary_packet_rejects_tampering(mutation):
    c=client();raw=bytearray(packet(c,'b'*32,'c'*32,DATA,1,b'a'*1024))
    index={'data':HEADER.size+15,'client':40,'signature':len(raw)-1,'length':HEADER.size-1,'unknown-op':4}.get(mutation)
    if index is not None:raw[index]^=127
    else:raw+=b'\0'
    with pytest.raises(Exception):unpack_packet(bytes(raw),c.private.public_key())


def signed_status(raw,c):
    return 'C71A2:'+base64.b64encode(raw).decode()+'.'+base64.b64encode(c.private.sign(raw,ec.ECDSA(hashes.SHA256()))).decode()


@pytest.mark.parametrize('mutation',['append','code','version','bytes','mask','signature'])
def test_ack_has_fixed_bounded_schema(mutation):
    c=client();args=[2,b'a'*16,b'b'*16,1,42,255,1,8192]
    raw=ACK.pack(*args);assert decode_status(signed_status(raw,c),c)['mask']==255
    if mutation=='append':raw+=b'secret'
    elif mutation=='signature':
        other=client()
        with pytest.raises(Exception):decode_status(signed_status(raw,other),c)
        return
    else:
        if mutation=='code':args[6]=250
        if mutation=='version':args[0]=1
        if mutation=='bytes':args[7]=MAX_BYTES+1
        if mutation=='mask':args[6]=0
        raw=ACK.pack(*args)
    with pytest.raises(ValueError):decode_status(signed_status(raw,c),c)


class NoSleep:
    def is_set(self):return False
    def wait(self,_):return False


@pytest.mark.parametrize('size',[64,1024,8192,8193,17000])
def test_sender_selectively_retries_missing_frames_and_validates_final(tmp_path,size):
    c=client();data=bytes(i%251 for i in range(size));path=tmp_path/'archive';path.write_bytes(data)
    meta={'bytes':size,'sha256':hashlib.sha256(data).hexdigest(),'key_id':'a'*16}
    session='b'*32;received={};seen=[];acks=[];dropped=False;polls=0
    def show(frame):
        nonlocal dropped,polls
        q=unpack_packet(frame.packet,c.private.public_key());op=q['op'];seq=q['seq'];seen.append((op,seq))
        status=dict(session=session,transfer=q['transfer'],base=seq,token=0,mask=0,code='ack',bytes=0)
        if op==BEGIN:acks.append(status)
        elif op==DATA:
            if seq==2 and not dropped:dropped=True;return
            received[seq]=q['body']
        elif op==POLL:
            polls+=1;status['token']=struct.unpack('>I',q['body'])[0]
            count=(size+1023)//1024
            status['mask']=sum(1<<i for i in range(min(8,count-seq+1)) if seq+i in received)
            status['bytes']=sum(map(len,received.values()));acks.append(status)
        elif op==END:
            assert b''.join(received[k] for k in sorted(received))==data
            status.update(code='stored',bytes=size,sha256=meta['sha256']);acks.append(status)
    result=transfer(c,path,meta,'テスト','d'*32,session,show,lambda:acks.pop(0) if acks else None,NoSleep())
    assert result['code']=='stored'
    if size>1024:
        assert seen.count((DATA,2))==2
        assert seen.count((DATA,1))==1
    assert polls==((size+8191)//8192)+(1 if size>1024 else 0)


def test_render_includes_full_quiet_zone_and_fits():
    c=client();frame=ColorFrame(packet(c,'b'*32,'c'*32,DATA,1,b'\x80'*1024))
    for size in (320,480,700):
        image=render_color(frame,size,size)
        assert image.width<=size and image.height<=size
        assert image.getpixel((0,0))==(255,255,255)
        assert decode_color_image(image)==frame.packet


def test_does_not_compress_or_remove_signature_from_binary_data():
    c=client();body=bytes(range(256))*4;raw=packet(c,'b'*32,'c'*32,DATA,1,body)
    assert len(raw)<=1172
    assert body in raw
    assert unpack_packet(raw,c.private.public_key())['body']==body
