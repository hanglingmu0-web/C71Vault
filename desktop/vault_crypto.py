"""Versioned, authenticated encrypted archives. No recovery key is sent to Android."""
from __future__ import annotations
import base64
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import secrets
import shutil
import stat
import struct
import tempfile
import zipfile
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

MAGIC = b'C71VAULT1\n'
CHUNK = 1024 * 1024
MAX_PLAIN = 50 * 1024**3
MAX_FILES = 100000

def digest(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(CHUNK), b''): h.update(b)
    return h.hexdigest()

def key_id(key): return hashlib.sha256(key).hexdigest()[:16]

def _walk_error(error):
    # os.walk otherwise silently omits unreadable folders from a successful backup.
    raise error

def create_key(path):
    key = secrets.token_bytes(32)
    with open(path, 'x', encoding='utf-8') as f:
        json.dump({'format': 'C71Vault-Recovery-Key-1', 'key_id': key_id(key), 'key': base64.b64encode(key).decode()}, f, indent=2)
        f.flush(); os.fsync(f.fileno())
    return key

def load_key(path):
    if Path(path).stat().st_size > 4096: raise ValueError('復元鍵ファイルが大きすぎます')
    d = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    key = base64.b64decode(d['key'], validate=True)
    if d.get('format') != 'C71Vault-Recovery-Key-1' or len(key) != 32 or d.get('key_id') != key_id(key):
        raise ValueError('復元鍵の形式が違います')
    return key

def _derive(key, salt):
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=b'C71Vault-Archive-v1').derive(key)

def safe_name(name):
    if not name or '\\' in name or ':' in name or '\x00' in name or name.startswith('/'):
        raise ValueError('安全でないファイル名です')
    parts = name.split('/')
    reserved = {'CON','PRN','AUX','NUL',*(f'COM{i}' for i in range(1,10)),*(f'LPT{i}' for i in range(1,10))}
    for p in parts:
        if p in ('', '.', '..') or p.endswith((' ', '.')) or any(ord(x)<32 for x in p) or any(x in p for x in '<>"|?*') or p.split('.')[0].upper() in reserved:
            raise ValueError('安全でないWindowsファイル名です: '+name)
    return name

class _EncryptWriter(io.RawIOBase):
    def __init__(self, out, encryptor): self.out=out; self.enc=encryptor; self.position=0
    def writable(self): return True
    def seekable(self): return False
    def tell(self): return self.position
    def write(self, b):
        self.out.write(self.enc.update(bytes(b))); self.position += len(b); return len(b)
    def flush(self):
        if not self.out.closed: self.out.flush()

def selection_entries(sources):
    """Map selected files/folders to archive names without staging plaintext copies."""
    roots=[]
    for value in sources:
        p=Path(value).absolute()
        if p.is_symlink() or p.is_junction(): raise ValueError('リンク・ジャンクションは対象外です: '+str(p))
        p=p.resolve(strict=True)
        if p not in roots: roots.append(p)
    if not roots: raise ValueError('ファイルまたはフォルダを追加してください')
    roots=[p for p in roots if not any(q!=p and q.is_dir() and p.is_relative_to(q) for q in roots)]
    names=set();entries=[];directories=[]
    single_folder=len(roots)==1 and roots[0].is_dir()
    def add_name(name):
        name=safe_name(name)
        if name.casefold() in names: raise ValueError('選択した項目の保存名が重複しています: '+name)
        names.add(name)
        if len(names)>MAX_FILES: raise ValueError('項目数は10万以下にしてください')
        return name
    for root in roots:
        if root.is_file(): entries.append((root,add_name(root.name)));continue
        if not root.is_dir(): raise ValueError('通常ファイル・フォルダを指定してください')
        prefix='' if single_folder else add_name(root.name)+'/'
        if prefix: directories.append(prefix[:-1])
        for current,dirs,files in os.walk(root,followlinks=False,onerror=_walk_error):
            dirs.sort();files.sort()
            for name in dirs+files:
                p=Path(current)/name
                if p.is_symlink() or p.is_junction(): raise ValueError('リンク・ジャンクションは対象外です: '+str(p))
                rel=add_name(prefix+p.relative_to(root).as_posix())
                if name in dirs: directories.append(rel)
                else: entries.append((p,rel))
    return roots,entries,directories

def pack(source, destination, key, progress=lambda s: None):
    roots,entries,directories=selection_entries(source if isinstance(source,(list,tuple)) else [source])
    destination = Path(destination).absolute()
    if any(destination.is_relative_to(p) for p in roots): raise ValueError('出力先をバックアップ対象の中に置けません')
    salt,nonce=secrets.token_bytes(16),secrets.token_bytes(12)
    header=json.dumps({'version':1,'salt':base64.b64encode(salt).decode(),'nonce':base64.b64encode(nonce).decode(),'key_id':key_id(key)},separators=(',',':')).encode()
    aad=MAGIC+struct.pack('>I',len(header))+header
    enc=Cipher(algorithms.AES(_derive(key,salt)),modes.GCM(nonce)).encryptor(); enc.authenticate_additional_data(aad)
    part=destination.with_name(destination.name+'.partial')
    if part.exists() or destination.exists(): raise FileExistsError('出力ファイルが既に存在します')
    created=False
    manifest={'version':1,'source_name':roots[0].name if len(roots)==1 else '選択したファイル','files':[],'directories':directories}
    total=0; seen=set()
    try:
        with open(part,'xb') as out:
            created=True
            out.write(aad); writer=_EncryptWriter(out,enc)
            with zipfile.ZipFile(writer,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=3,allowZip64=True) as z:
                for p,rel in entries:
                    before=p.stat()
                    if not stat.S_ISREG(before.st_mode): raise ValueError('通常ファイルではありません: '+str(p))
                    if rel.casefold() in seen: raise ValueError('大文字小文字だけが違う名前です: '+rel)
                    seen.add(rel); total+=before.st_size
                    if len(seen)>MAX_FILES or total>MAX_PLAIN: raise ValueError('対象は10万ファイル・非圧縮50GiB以下にしてください')
                    progress('暗号化中: '+rel)
                    h=hashlib.sha256(); count=0
                    with open(p,'rb') as src,z.open('files/'+rel,'w',force_zip64=True) as entry:
                        for b in iter(lambda:src.read(CHUNK),b''):
                            count+=len(b)
                            if count>before.st_size: raise ValueError('バックアップ中にファイルが変更されました: '+rel)
                            h.update(b);entry.write(b)
                    after=p.stat()
                    if (before.st_size,before.st_mtime_ns,before.st_ino)!=(after.st_size,after.st_mtime_ns,after.st_ino) or count!=before.st_size:
                        raise ValueError('バックアップ中にファイルが変更されました: '+rel)
                    manifest['files'].append({'path':rel,'bytes':count,'sha256':h.hexdigest(),'mtime_ns':before.st_mtime_ns})
                manifest_bytes=json.dumps(manifest,ensure_ascii=False,separators=(',',':')).encode('utf-8')
                if len(manifest_bytes)>32*1024**2: raise ValueError('目録が32MiBを超えています。対象を分割してください')
                z.writestr('manifest.json',manifest_bytes)
            out.write(enc.finalize());out.write(enc.tag);out.flush();os.fsync(out.fileno())
        if destination.exists(): raise FileExistsError(destination)
        os.rename(part,destination)
        return {'sha256':digest(destination),'bytes':destination.stat().st_size,'key_id':key_id(key),'file_count':len(seen),'plain_bytes':total}
    finally:
        if created: part.unlink(missing_ok=True)

def _decrypt(archive, out, key):
    with open(archive,'rb') as src:
        if src.read(len(MAGIC))!=MAGIC: raise ValueError('C71 Vaultのバックアップではありません')
        raw_len=src.read(4)
        if len(raw_len)!=4: raise ValueError('不完全なヘッダーです')
        n=struct.unpack('>I',raw_len)[0]
        if not 2<=n<=1024: raise ValueError('ヘッダー長が不正です')
        raw=src.read(n); header=json.loads(raw)
        if header['version']!=1 or header['key_id']!=key_id(key): raise ValueError('復元鍵が一致しません')
        salt=base64.b64decode(header['salt'],validate=True);nonce=base64.b64decode(header['nonce'],validate=True)
        if len(salt)!=16 or len(nonce)!=12: raise ValueError('暗号形式が不正です')
        start=src.tell();src.seek(0,2);end=src.tell()
        if end-start<16: raise ValueError('不完全な暗号データです')
        src.seek(-16,2);tag=src.read(16);src.seek(start)
        dec=Cipher(algorithms.AES(_derive(key,salt)),modes.GCM(nonce,tag)).decryptor();dec.authenticate_additional_data(MAGIC+raw_len+raw)
        remaining=end-start-16
        while remaining:
            b=src.read(min(CHUNK,remaining))
            if not b: raise ValueError('転送が途中で終わっています')
            out.write(dec.update(b));remaining-=len(b)
        out.write(dec.finalize());out.flush()

def restore(archive, destination, key, progress=lambda s: None):
    destination=Path(destination).absolute()
    if destination.exists(): raise FileExistsError('復元先は存在しない新規フォルダを指定してください')
    destination.parent.mkdir(parents=True,exist_ok=True)
    # Authenticate the entire ciphertext before opening ZIP or creating any restored files.
    with tempfile.TemporaryFile() as plain:
        _decrypt(archive,plain,key);plain.seek(0)
        with zipfile.ZipFile(plain) as z:
            infos=z.infolist()
            if len(infos)>MAX_FILES+1: raise ValueError('ZIPのファイル数が上限を超えています')
            names=[x.filename for x in infos]
            if len(names)!=len(set(names)) or 'manifest.json' not in names: raise ValueError('ZIPの目録が不正です')
            if z.getinfo('manifest.json').file_size>32*1024**2: raise ValueError('目録が大きすぎます')
            m=json.loads(z.read('manifest.json'))
            if m.get('version')!=1 or not isinstance(m.get('files'),list): raise ValueError('目録の形式が違います')
            if len(m['files'])>MAX_FILES or len(m.get('directories',[]))>MAX_FILES: raise ValueError('項目数が多すぎます')
            expected={'manifest.json'}; seen=set(); total=0
            for f in m['files']:
                p=safe_name(f['path']); folded=p.casefold()
                if folded in seen: raise ValueError('ファイル名の重複があります')
                seen.add(folded);expected.add('files/'+p)
                size=f['bytes']
                if type(size)!=int or size<0 or z.getinfo('files/'+p).file_size!=size: raise ValueError('サイズが目録と一致しません')
                total+=size
                if total>MAX_PLAIN: raise ValueError('復元サイズが50GiBを超えています')
                if (z.getinfo('files/'+p).external_attr>>16)&0o170000==0o120000: raise ValueError('リンクは復元しません')
            if set(names)!=expected: raise ValueError('目録にないファイルがあります')
            dirs=[safe_name(d) for d in m.get('directories',[])]
            if any(d.casefold() in seen for d in dirs): raise ValueError('ファイルとフォルダの名前が衝突しています')
            if shutil.disk_usage(destination.parent).free<total+256*1024**2: raise ValueError('PCの復元先の空き容量が足りません')
            tmp=Path(tempfile.mkdtemp(prefix='.c71-restore-',dir=destination.parent))
            try:
                for d in dirs:(tmp/Path(d)).mkdir(parents=True,exist_ok=True)
                for f in m['files']:
                    progress('復元・照合中: '+f['path']);p=tmp/Path(f['path']);p.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256();count=0
                    with z.open('files/'+f['path']) as inp,open(p,'xb') as out:
                        for b in iter(lambda:inp.read(CHUNK),b''):
                            count+=len(b)
                            if count>f['bytes']:raise ValueError('展開サイズ超過です')
                            h.update(b);out.write(b)
                        out.flush();os.fsync(out.fileno())
                    if count!=f['bytes'] or h.hexdigest()!=f['sha256']: raise ValueError('復元ファイルが元データと一致しません: '+f['path'])
                    os.utime(p,ns=(f['mtime_ns'],f['mtime_ns']))
                os.rename(tmp,destination)
                return {'files':len(m['files']),'bytes':total,'destination':str(destination)}
            finally:
                if tmp.exists():shutil.rmtree(tmp)
