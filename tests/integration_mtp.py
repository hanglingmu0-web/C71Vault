"""Run against a physically paired test device. Only generated fixtures are backed up."""
import json
import os
from pathlib import Path
import sys
import time
import uuid
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'desktop'))
from vault_crypto import create_key,pack,restore,digest
from vault_client import Client
from vault_transport import MtpBridge

def main():
    root=Path(sys.argv[1]).absolute();root.mkdir(parents=True,exist_ok=True)
    source=root/'source';source.mkdir(exist_ok=True)
    (source/'日本語フォルダ').mkdir(exist_ok=True)
    (source/'空のフォルダ').mkdir(exist_ok=True)
    (source/'日本語フォルダ'/'契約書.txt').write_text('これは実機検証用の架空の契約書です。金額330円。\n'*300,encoding='utf-8')
    (source/'random.bin').write_bytes(os.urandom(32*1024**2+137))
    (source/'empty.txt').write_bytes(b'')
    key=create_key(root/'test-only.c71key');archive=root/'original.c71b'
    meta=pack(source,archive,key)
    c=Client(MtpBridge(),state=Path(sys.argv[2]) if len(sys.argv)>2 else root.parent/'integration-state',log=lambda x:print(x,flush=True));c.read_device()
    start=time.monotonic();saved=c.backup(archive,meta,'実機検証用・架空データ');stored_seconds=time.monotonic()-start
    assert any(a['id']==saved['id'] for a in c.list())
    received=root/'received.c71b';start=time.monotonic();c.download(saved['id'],received);download_seconds=time.monotonic()-start
    restored=root/'restored';result=restore(received,restored,key)
    for p in source.rglob('*'):
        if p.is_file():assert digest(p)==digest(restored/p.relative_to(source))
    # Deliberately replace the source data; recovery must still restore the saved version.
    (source/'日本語フォルダ'/'契約書.txt').write_text('意図的な上書き後の内容',encoding='utf-8')
    received2=root/'received-after-overwrite.c71b';c.download(saved['id'],received2)
    assert digest(received2)==meta['sha256']
    checks={}
    for op in ['delete','overwrite','clear','prune']:
        try:c.request({'op':op,'id':saved['id']},timeout=30)
        except RuntimeError as e:checks[op]=str(e)
        else:raise AssertionError(op+' was accepted')
    q=dict(op='store',id=saved['id'],bytes=meta['bytes'],sha256='0'*64,key_id=meta['key_id'],label='overwrite attempt')
    try:c.request(q,timeout=30)
    except RuntimeError as e:checks['same_id']=str(e)
    else:raise AssertionError('overwrite by reused id was accepted')
    # Another unregistered Windows identity cannot list or export the data.
    untrusted=Client(MtpBridge(),state=root/'untrusted-state');untrusted.read_device()
    try:untrusted.request({'op':'list'},timeout=30)
    except RuntimeError as e:checks['unregistered']=str(e)
    else:raise AssertionError('unregistered client accepted')
    final=root/'after-attacks.c71b';c.download(saved['id'],final);assert digest(final)==meta['sha256']
    report={'archive_id':saved['id'],'encrypted_bytes':meta['bytes'],'plaintext_files':result['files'],'sha256':meta['sha256'],'store_seconds':round(stored_seconds,2),'download_seconds':round(download_seconds,2),'checks':checks,'all_restored_files_match':True,'saved_version_survives_source_overwrite':True,'saved_version_survives_denied_operations':True,'transport':'Windows MTP Shell / Android SAF; data did not use ADB'}
    (root/'result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':main()
