import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
import base64,json,secrets,hashlib,struct
from types import SimpleNamespace
import pytest
from cryptography.hazmat.primitives import serialization,hashes
from cryptography.hazmat.primitives.asymmetric import ec,rsa
from vault_recovery import escrow,recover,oaep,custody_public_key
from vault_crypto import key_id,load_key
from vault_optical import frames,decode_status,CHUNK
from vault_client import Client

def signed(payload,private):
    raw=json.dumps(payload,separators=(',',':')).encode()
    return {'payload':base64.b64encode(raw).decode(),'signature':base64.b64encode(private.sign(raw,ec.ECDSA(hashes.SHA256()))).decode()}

def test_custody_capsule_is_encrypted_and_authenticates_device_key():
    signer=ec.generate_private_key(ec.SECP256R1());wrapping=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    pub=wrapping.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    info={'recovery_public_key':base64.b64encode(pub).decode(),'recovery_key_signature':base64.b64encode(signer.sign(pub,ec.ECDSA(hashes.SHA256()))).decode()}
    key=secrets.token_bytes(32);seen=[]
    def request(q,**kw):
        seen.append(q);assert wrapping.decrypt(base64.b64decode(q['capsule']),oaep())==key
        return {'key_id':key_id(key),'custody_verified':True}
    c=SimpleNamespace(device=info,device_key=signer.public_key(),log=lambda x:None,request=request)
    assert escrow(c,key)['custody_verified']
    assert base64.b64encode(key).decode() not in json.dumps(seen)
    info['recovery_key_signature']=base64.b64encode(b'bad').decode()
    with pytest.raises(Exception):custody_public_key(info,c.device_key)

def test_new_pc_can_recover_to_its_ephemeral_key_without_old_pc_private_key(tmp_path):
    key=secrets.token_bytes(32)
    def request(q,**kw):
        recipient=serialization.load_der_public_key(base64.b64decode(q['recipient']))
        return {'key_id':key_id(key),'capsule':base64.b64encode(recipient.encrypt(key,oaep())).decode()}
    c=SimpleNamespace(log=lambda x:None,request=request)
    path=tmp_path/'recovered.c71key';assert recover(c,key_id(key),path)==key_id(key)
    assert load_key(path)==key
    with pytest.raises(FileExistsError):recover(c,key_id(key),path)

def test_wrong_recovered_key_never_creates_key_file(tmp_path):
    key=secrets.token_bytes(32)
    def request(q,**kw):
        recipient=serialization.load_der_public_key(base64.b64decode(q['recipient']))
        return {'key_id':key_id(key),'capsule':base64.b64encode(recipient.encrypt(secrets.token_bytes(32),oaep())).decode()}
    with pytest.raises(ValueError):recover(SimpleNamespace(log=lambda x:None,request=request),key_id(key),tmp_path/'key')
    assert not (tmp_path/'key').exists()

def test_optical_frames_reconstruct_exact_bytes_and_have_valid_signatures(tmp_path):
    c=Client(None,tmp_path/'state');path=tmp_path/'archive';data=secrets.token_bytes(CHUNK*3+79);path.write_bytes(data)
    meta={'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'key_id':'1'*16}
    decoded=[]
    for seq,text in frames(c,path,meta,'光学試験','a'*32,'b'*32,'c'*32):
        assert len(text)<2331
        env=json.loads(text[6:]);raw=base64.b64decode(env['payload']);c.private.public_key().verify(base64.b64decode(env['signature']),raw,ec.ECDSA(hashes.SHA256()))
        p=json.loads(raw);assert p['seq']==seq;decoded.append(p)
    assert decoded[0]['op']=='begin' and decoded[-1]['op']=='end'
    assert b''.join(base64.b64decode(p['data']) for p in decoded[1:-1])==data

@pytest.mark.parametrize('mutation',['extra-data','bad-signature','wrong-device','unknown-code','invalid-bytes'])
def test_optical_status_rejects_non_ack_schema(mutation):
    key=ec.generate_private_key(ec.SECP256R1());c=SimpleNamespace(device={'device':'phone'},device_key=key.public_key())
    def wrap(raw):return 'C71A1:'+base64.b64encode(raw).decode()+'.'+base64.b64encode(key.sign(raw,ec.ECDSA(hashes.SHA256()))).decode()
    raw=struct.pack('>B16s16siBQ',1,bytes.fromhex('a'*32),b'\0'*16,-1,0,0)
    assert decode_status(wrap(raw),c)['code']=='ready'
    if mutation=='extra-data':raw+=b'secret'
    elif mutation=='wrong-device':c.device_key=ec.generate_private_key(ec.SECP256R1()).public_key()
    elif mutation=='unknown-code':raw=struct.pack('>B16s16siBQ',1,b'a'*16,b'\0'*16,-1,255,0)
    elif mutation=='invalid-bytes':raw=struct.pack('>B16s16siBQ',1,b'a'*16,b'\0'*16,-1,0,2**63)
    frame=wrap(raw)
    if mutation=='bad-signature':frame=frame.rsplit('.',1)[0]+'.'+base64.b64encode(b'bad').decode()
    with pytest.raises(Exception):decode_status(frame,c)

@pytest.mark.parametrize('size',[320,480,700])
def test_qr_fits_small_window_without_cropping(tmp_path,size):
    from vault_qr import render_qr
    import zxingcpp
    c=Client(None,tmp_path/'state');p=tmp_path/'a';p.write_bytes(secrets.token_bytes(512))
    meta={'bytes':512,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'key_id':'a'*16}
    for _,text in frames(c,p,meta,'読み取り試験','a'*32,'b'*32,'c'*32):
        image=render_qr(text,size,size)
        assert image.width<=size and image.height<=size
        assert zxingcpp.read_barcode(image).text==text
