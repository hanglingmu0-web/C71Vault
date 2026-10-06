"""Phone custody uses RSA-OAEP capsules. Plaintext keys never enter MTP staging."""
import base64
import json
import os
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding, ec
from vault_crypto import key_id

def oaep():
    # Explicit Android Keystore-compatible MGF1 digest.
    return padding.OAEP(mgf=padding.MGF1(hashes.SHA1()), algorithm=hashes.SHA256(), label=None)

def custody_public_key(device, signing_key):
    if 'recovery_public_key' not in device:
        raise ValueError('C71を更新し、PIN等の画面ロックを設定してください')
    raw=base64.b64decode(device['recovery_public_key'],validate=True)
    signing_key.verify(base64.b64decode(device['recovery_key_signature'],validate=True),raw,ec.ECDSA(hashes.SHA256()))
    public=serialization.load_der_public_key(raw)
    if not isinstance(public,rsa.RSAPublicKey) or public.key_size!=2048:
        raise ValueError('C71の鍵保管用公開鍵が不正です')
    return public

def escrow(client,key):
    pub=custody_public_key(client.device,client.device_key)
    capsule=base64.b64encode(pub.encrypt(key,oaep())).decode()
    client.log('復元鍵をC71に保管します。初回はC71で端末認証してください。')
    r=client.request({'op':'escrow','key_id':key_id(key),'capsule':capsule},timeout=600)
    if r.get('key_id')!=key_id(key) or r.get('custody_verified') is not True:
        raise ValueError('C71での復元鍵の保管を確認できませんでした')
    return r

def recover(client,id,destination):
    # Recipient private key exists only for this recovery operation, including on a new PC.
    private=rsa.generate_private_key(public_exponent=65537,key_size=2048)
    der=private.public_key().public_bytes(serialization.Encoding.DER,serialization.PublicFormat.SubjectPublicKeyInfo)
    client.log('C71で鍵の回収を承認し、端末認証してください。')
    r=client.request({'op':'recover_key','key_id':id,'recipient':base64.b64encode(der).decode()},timeout=600)
    if r.get('key_id')!=id:raise ValueError('回収する鍵IDが一致しません')
    key=private.decrypt(base64.b64decode(r['capsule'],validate=True),oaep())
    if len(key)!=32 or key_id(key)!=id:raise ValueError('回収した復元鍵が一致しません')
    with open(destination,'x',encoding='utf-8') as f:
        json.dump({'format':'C71Vault-Recovery-Key-1','key_id':id,'key':base64.b64encode(key).decode()},f,indent=2)
        f.flush();os.fsync(f.fileno())
    return id
