# Third-party components

## 0.4のMIDI受信追加依存

- Android USB serial: **usb-serial-for-android v3.10.0**, MIT。
  上流タグの`src/main`を`android/usbSerialForAndroid/`へ収録。Javaソースは変更せず、このプロジェクト用のGradle設定を使用しています。
  ライセンス全文：`licenses/usb-serial-for-android-3.10.0-MIT.txt`。
  CDC/ACM、FTDI、CH340/341、CP210x、PL2303等のドライバを含みます。全機器・全baudでの実機確認を意味しません。
- AndroidX annotation **1.9.1**（Apache-2.0）：上記ライブラリの依存。
- 解決済みAndroid runtime依存にはKotlin stdlib **2.2.10** とJetBrains annotations **13.0**（いずれもApache-2.0）も含まれます。ライセンスは`licenses/`に収録しています。
- 開発用PC中継スクリプト：**pyserial 3.5**（BSD-3-Clause）。通常のWindows EXEには追加していません。
- Arduino CLIによる実機試験：Arduino AVR core **1.8.8**、Renesas UNO core **1.6.0**。Arduinoのコア・ツール一式はこの配布物に同梱していません。

USB MIDI入力はAndroid標準の`android.media.midi`を使用します。MIDI SysExの符号化に外部ライブラリは使っていません。

Windows版はPython 3.14.5、Tcl/Tk、pywin32、cryptographyとその依存ライブラリを同梱します。ライセンス本文は `licenses/` と `windows/C71Vault/_internal/cryptography-48.0.0.dist-info/licenses/` に収録しています。PythonのLICENSEには同梱ライブラリの関連通知も含まれます。PyInstaller 6.22.3による配布です。

- cryptography 48.0.0
- pywin32 311
- cffi 2.0.0
- pycparser 3.0
- bcrypt 5.0.0

Android 0.1配布版の実装はAndroid標準APIを使用していました。0.2の配布APKは、下記のQRライブラリとAndroidX依存も含みます。AndroidXのテスト用runnerは開発用テストAPKだけで使用します。

## 0.2の追加依存

- qrcode 8.2
- Pillow 12.2.0
- opencv-python 4.13.0.92
- numpy 2.4.6
- zxing-cpp 3.1.1

Android: ZXing Android Embedded 4.3.0、ZXing CoreとAndroidX依存を配布APKで使用します。Android版も第三者ライブラリを含みます。各ライブラリのライセンス本文は `licenses/` に収録しています。


## 0.5.0 desktop MIDI support

The Windows executable now bundles pyserial 3.5 (BSD-3-Clause). Its license is included in `licenses/pyserial-3.5-LICENSE.txt`. Drag and drop uses Windows system APIs; no new drag-and-drop library is included.
