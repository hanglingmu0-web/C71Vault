"""Windows MTP using synchronous IFileOperation; no ADB, driver or network service."""
from __future__ import annotations
import os
from pathlib import Path
import re
import shutil
import tempfile
import win32com.client
import pythoncom
from win32com.shell import shell, shellcon


def valid_name(name):
    if not re.fullmatch(r'(device\.json|[qrbx]-[0-9a-f]{32}\.(json|c71b))', name):
        raise ValueError('不正な転送ファイル名')
    return name


class MtpBridge:
    def __init__(self, device_name=None):
        pythoncom.CoInitialize()
        self.shell = win32com.client.Dispatch('Shell.Application')
        candidates = []
        for item in self.shell.NameSpace(17).Items():
            if item.IsFileSystem or (device_name and device_name not in item.Name):
                continue
            try:
                for storage in item.GetFolder.Items():
                    if not storage.IsFolder:
                        continue
                    documents = storage.GetFolder.ParseName('Documents')
                    if documents is None:
                        continue
                    vault = documents.GetFolder.ParseName('C71Vault')
                    if vault is not None:
                        candidates.append((item.Name, vault))
            except Exception:
                continue
        if not candidates:
            raise RuntimeError('C71をPCへUSB接続し、ロック解除してUSBの用途を「ファイル転送」にしてください。通常版C71 VaultでUSB受信を開始してください。初回のみUSB受渡しフォルダの設定が必要です。MIDIで保存した版も、最新の一覧取得・復元にはこのUSB接続が必要です。')
        if len(candidates) != 1:
            raise RuntimeError('C71 Vault対応端末が複数あります。使う端末だけを接続してください。')
        self.name, self.vault_item = candidates[0]

    def folder(self):
        return self.vault_item.GetFolder

    def item(self, name):
        return self.folder().ParseName(valid_name(name))

    def has(self, name):
        return self.item(name) is not None

    @staticmethod
    def portable_item(folder_item):
        pidl = shell.SHGetIDListFromObject(folder_item._oleobj_)
        return shell.SHCreateItemFromIDList(pidl, shell.IID_IShellItem)

    @staticmethod
    def filesystem_item(path):
        return shell.SHCreateItemFromParsingName(str(Path(path).absolute()), None, shell.IID_IShellItem)

    @staticmethod
    def copy(source, folder, name):
        operation = pythoncom.CoCreateInstance(shell.CLSID_FileOperation, None, pythoncom.CLSCTX_INPROC_SERVER, shell.IID_IFileOperation)
        operation.SetOperationFlags(shellcon.FOF_NO_UI | shellcon.FOFX_EARLYFAILURE)
        operation.CopyItem(source, folder, name, None)
        operation.PerformOperations()
        if operation.GetAnyOperationsAborted():
            raise ConnectionError('USB転送が中止されました。保存成功として扱いません')

    def send_request(self, source):
        source = Path(source).absolute()
        valid_name(source.name)
        # The phone may consume the request immediately. Its signed response is the acknowledgement.
        self.copy(self.filesystem_item(source), self.portable_item(self.vault_item), source.name)

    def upload(self, source, name, **kwargs):
        valid_name(name)
        if self.has(name):
            raise FileExistsError('同じ転送IDが既にあります')
        self.copy(self.filesystem_item(source), self.portable_item(self.vault_item), name)
        if not self.has(name):
            raise ConnectionError('USB転送先にデータが見つかりません')

    def download(self, name, destination, timeout=1800, max_bytes=None, expected_bytes=None):
        valid_name(name)
        destination = Path(destination).absolute()
        item = self.item(name)
        if item is None:
            raise FileNotFoundError(name)
        declared = int(item.ExtendedProperty('System.Size') or 0)
        if max_bytes is not None and declared > max_bytes:
            raise ValueError('受信サイズが上限を超えています')
        if destination.exists():
            raise FileExistsError(destination)
        with tempfile.TemporaryDirectory(prefix='c71-mtp-') as directory:
            self.copy(self.portable_item(item), self.filesystem_item(directory), name)
            copied = Path(directory) / name
            if not copied.is_file():
                raise ConnectionError('USB受信が完了していません')
            actual = copied.stat().st_size
            if max_bytes is not None and actual > max_bytes:
                raise ValueError('受信サイズが上限を超えています')
            if expected_bytes is not None and actual != expected_bytes:
                raise ValueError('受信サイズがC71の署名付き応答と一致しません')
            with copied.open('rb') as inp, destination.open('xb') as out:
                shutil.copyfileobj(inp, out, 1024 * 1024)
                out.flush()
                os.fsync(out.fileno())

    def read(self, name, max_bytes=8 * 1024 * 1024):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / name
            self.download(name, path, max_bytes=max_bytes)
            return path.read_bytes()


class FolderBridge:
    """Local protocol simulator for tests; never presented as a protected device."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)
        self.name = 'TEST DIRECTORY'

    def has(self, name):
        return (self.path / valid_name(name)).exists()

    def send_request(self, source):
        self.upload(source, Path(source).name)

    def upload(self, source, name, **kwargs):
        path = self.path / valid_name(name)
        if path.exists():
            raise FileExistsError(path)
        shutil.copyfile(source, path)

    def download(self, name, destination, **kwargs):
        source = self.path / valid_name(name)
        if source.stat().st_size > kwargs.get('max_bytes', float('inf')):
            raise ValueError('size')
        shutil.copyfile(source, destination)

    def read(self, name, max_bytes=8 * 1024 * 1024):
        path = self.path / valid_name(name)
        if path.stat().st_size > max_bytes:
            raise ValueError('size')
        return path.read_bytes()
