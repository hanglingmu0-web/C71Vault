# ビルド・開発手順

## Windows

検証環境: Windows 11 x64、Python 3.14.5、PyInstaller 6.22.3。Python 3.12以降を想定しています。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r desktop\requirements.txt pyinstaller
.\.venv\Scripts\python.exe -m pytest tests -q -W error
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --windowed --onedir --name C71Vault --distpath windows desktop\app.py
```

開発用に `python desktop/app.py` でも起動できます。Windowsのログインユーザーのコンテキストで実行してください。DPAPI認証情報は別ユーザーに移せません。管理者権限は不要です。

Windows 0.5.3の通常の自己テストはオフラインです。USB/MTPの確認は別のオプションで実行します。結果は指定したJSONファイルへ保存します。

```powershell
.\windows\C71Vault-0.5.3\C71Vault.exe --self-test "$PWD\self-test.json"
.\windows\C71Vault-0.5.3\C71Vault.exe --self-test-mtp "$PWD\mtp-self-test.json"
.\windows\C71Vault-0.5.3\C71Vault.exe --drop-self-test "$PWD\drop-self-test.json"
```

MTPテストのみ、C71のUSB接続・ファイル転送・USB受付開始が必要です。自己テストは実データのバックアップを行いません。

## Android

検証環境: Android Studio付属JBR、Gradle 9.3.1、Android Gradle Plugin 9.0.1、SDK 36、build-tools 36.0.0。最小Androidは11（API 30）です。Gradle本体・SDKは同梱していません。`JAVA_HOME` と `ANDROID_HOME` を設定し、Android Studioで `android/` を開くか、以下を実行します。

```powershell
cd android
gradle assembleDebug assembleDebugAndroidTest assembleRelease lintRelease
```

開発版のアプリIDは `jp.c71.vault.dev`、配布版は `jp.c71.vault` です。同じ転送フォルダを使うため、受信サービスは片方だけ開始してください。

端末上の自動テストは開発用パッケージ内だけに試験データを作ります。

```powershell
adb install -r app\build\outputs\apk\debug\app-debug.apk
adb install -r app\build\outputs\apk\androidTest\debug\app-debug-androidTest.apk
adb shell am instrument -w jp.c71.vault.dev.test/androidx.test.runner.AndroidJUnitRunner
```

配布APKは `apksigner` で署名します。更新では同じ証明書が必要です。秘密の署名用キーストアは配布物・ソースZIPに含めていません。この作業環境の `work/signing/` に保管しています。バックアップの復元鍵とは別の鍵です。

同梱APKの署名証明書SHA-256:

`21a7cfa603f6b9227291becdd2f693949233136636bfb7ff13a2bfed3196b84c`

## USB実機テスト

`tests/integration_mtp.py` は、新規の試験ディレクトリと登録済みPC状態ディレクトリを引数に取ります。32MiBの乱数ファイルと架空の日本語文書等を作り、USBで保存・復元した上で削除・上書き要求が拒否されることを確認します。実データのあるPC状態を試験のために削除しないでください。

## データ形式

バックアップは `C71VAULT1\n` + big-endian 32-bitヘッダー長 + JSONヘッダー + AES-GCM暗号文 + 16-byte tagです。ヘッダーはversion/salt/nonce/key_idを持ち、ヘッダーまでのバイト列をAADにします。平文はZIPで、`manifest.json` と `files/` 内の文書を含みます。独自形式のため、復元用ソースと鍵をバックアップデータとともに別途保管してください。

USB転送フォルダは `device.json`（公開情報）、`q-ID.json`（署名付き要求）、`r-ID.json`（署名付き応答）、`b-ID.c71b`（保存待ち）、`x-ID.c71b`（復元用書き出し）を使用します。署名は生のJSON UTF-8バイト列に対するECDSA-SHA256です。

## 0.2の追加実装

- `RecoveryKeys.java` / `vault_recovery.py`: RSA-OAEPの鍵カプセル、Keystoreの端末認証、回収先一時鍵への包み直し。
- `Retention.java`: 削除を行わない純粋な保持候補計算。`Vault.applyRetention` が認証後の実行時に再計算します。
- `OpticalReceiver.java` / `OpticalActivity.java` / `vault_optical.py`: ZXingのQR、署名付き512-byteフレーム、連番と再送、ACKの限定。
- 光学データ接頭辞は `C71O1:`、以降は署名付きJSON envelopeです。ACKは `C71A1:` + base64(固定長バイナリ) + `.` + base64(ECDSA署名)です。署名対象はバイナリそのものです。
- ACKの通常ペイロードは46 bytes: version u8、session 16 bytes、transfer 16 bytes、seq i32、状態コードu8、受信量u64（整数はbig-endian）。保存完了時だけ末尾にSHA-256の32 bytesを付加します。端末は登録済み署名鍵で識別します。未知の長さ・コード・追記データを拒否します。
- セッションはC71が光学画面を開くごとに生成し、1画面で1転送だけを受け付けます。QRはウィンドウ領域に合わせて整数倍で描画し、四辺の余白ごと表示します。
- 機密データや鍵を返す操作はUSBの分岐にだけ存在し、光学受信は `begin/data/end` 以外を拒否します。

Windowsの配布にはqrcode/Pillow、OpenCV、zxing-cppを追加しています。AndroidにはZXing Android Embedded 4.3.0とその依存を追加しています。バイナリを配布する際は `licenses/` と第三者通知も含めてください。


## 0.3の追加実装

- `vault_color.py`: 1,024-byteバイナリ署名フレーム、4色2層QR、8枚まとめACK、選択再送。
- `ColorCode.java`: NV21の赤・青成分による2層復号と共通位置情報の利用。
- `ColorOpticalReceiver.java`: 最大8KiBの受信窓、署名検証、まとめACK、保存確定。
- `ColorOpticalActivity.java`: 高解像度を優先する前面カメラ、白黒ACK表示。
- 従来の `vault_optical.py` / `OpticalReceiver.java` は引き続き使用できます。
- 新しい外部ライブラリは追加していません。`OPTICAL_V2.md` に独自形式を記載しています。

Androidの `src/androidTest/assets/color-*` は人工的な試験パケット・画像・公開鍵です。秘密鍵や利用者の撮影画像は含みません。

## MIDI additions (0.4.0)

The Android project includes the pinned MIT usb-serial-for-android 3.10.0 main
sources as a local Gradle library module. No JitPack resolution is needed.
See `android/usbSerialForAndroid/UPSTREAM.md` and `THIRD_PARTY.md`.

`SerialFrame` handles MIDI 1.0 SysEx/7-bit framing; `IsolatedReceiver` handles
sessions and integrity checks; `MidiBackupSink` adapts authenticated writes to
the existing vault; `IsolatedSerialActivity` selects Android USB serial/MIDI
inputs. `DevelopmentSerialPipe` lives in `src/debug` only.

The existing desktop EXE is unchanged. MIDI CLI tools are in `desktop/`, and
Arduino sketches in `arduino/`. Extract the source ZIP to use those Python
tools. `requirements-midi-dev.txt` adds pyserial for PC COM-port access.


## 0.5.0 additions

`desktop/app.py` now starts `TransferApp` from `transfer_ui.py`. `windows_drop.py` handles Explorer WM_DROPFILES on Windows x64 without an additional dependency. The desktop bundle includes pyserial 3.5. `python tests/ui_smoke.py report.json` creates an isolated GUI instance and injects a native Unicode multi-file drop, then verifies transport controls without sending data.
