# 検証結果 — 2026-10-01

## Publication evidence index

Publication packaging note: local usernames in diagnostic paths have been replaced with `LOCAL_USER`; numerical test results and payload hashes are unchanged. Original device screenshots are omitted because their codes may contain live protocol data; only the explicitly labeled public examples are included. Historical references to those screenshots identify local evidence, not published assets. Distribution EXE/APK checksums refer to the files in the release bundle. The published checksum manifest was regenerated after this packaging step.

This index was added on 2026-10-06 for the initial publication. Test dates below come from the existing dated validation entries, not filesystem timestamps. The compact reports do not preserve exact execution times or a complete machine/environment snapshot; those details cannot be reconstructed from these reports. Adding this index does not represent a new test run.

| Claim | Recorded test date | Recorded environment and scope | Public evidence |
|---|---|---|---|
| 90 Python tests passed | 2026-10-01 | Windows 11 x64, Python 3.14.5 as recorded in BUILD.md; Windows 0.5.3 source | [pytest output](validation/python-tests-v053.txt) |
| Packaged offline self-test passed | 2026-10-01 | Windows 0.5.3 EXE; OpenCV 4.13.0 reported; MTP explicitly not requested | [self-test report](validation/exe-self-test-v053.json) |
| 53 asynchronous native drop messages passed | 2026-10-01 | Packaged Windows 0.5.3 EXE, native WM_DROPFILES under Tk mainloop; no transfer | [drop report](validation/exe-drop-v053.json) |
| Signed MIDI commit verified locally | 2026-09-30 | PC 0.5.2 → UNO R3 → two PS817C optocouplers → UNO R4 WiFi → USB-C/OTG → realme C71 normal app 0.5.0; UART 9600, USB serial 115200 | [sanitized commit verification report](validation/normal-midi-commit-result.json) |
| MIDI-saved Word document restored and hash matched | 2026-10-01 | PC 0.5.3 and C71 normal app 0.5.0; direct USB/MTP restoration | [restore report](validation/midi-usb-restore-v053.json) |

The Windows build environment is recorded in [BUILD.md](BUILD.md) as Windows 11 x64, Python 3.14.5 and PyInstaller 6.22.3. The hardware records identify the phone as realme C71 (RMX5303). Exact Windows build, Android OS build/security patch, and full dependency versions are not captured in these particular reports. Board core versions recorded during development were AVR 1.8.8 and Renesas 1.6.0; this is not a per-run environment attestation.

### Artifact checksums and their meaning

[PUBLICATION_SHA256SUMS.txt](validation/PUBLICATION_SHA256SUMS.txt) contains SHA-256 checksums computed on 2026-10-06 for the reports above, this validation document, the publication draft, referenced documentation and source files, and the current Windows EXE/Android APK. Paths are relative to the project root. These hashes identify the files prepared for publication. They are not original test-time attestations, and the EXE checksum does not cover its required `_internal` directory.

The recorded MIDI encrypted archive SHA-256 is `f5ce1daa3d833e0501c5c6acfb82289de870fa257f5a568e41d8ea5e751e9768`. Both the commit and USB restore reports contain that value. It is the archive hash, not a report-file checksum. The restore report records plaintext equality as a boolean; the original Word document and its individual plaintext hash are not published.

The commit report is a sanitized result of a separate local signature check. The original signed ACK and its verification inputs are not included in the public evidence, so this report alone does not allow an external reader to reproduce that signature verification. No third-party audit is claimed. Likewise, a checksum of a test report establishes file identity, not the truth of its contents.

### Repeating the software checks

From the project root, in a Windows Python environment prepared using [BUILD.md](BUILD.md), use fresh output paths:

```powershell
python -m pytest tests -q -W error -p no:cacheprovider --basetemp .test-tmp-publication
.\windows\C71Vault-0.5.3\C71Vault.exe --self-test "$PWD\self-test-publication.json"
.\windows\C71Vault-0.5.3\C71Vault.exe --drop-self-test "$PWD\drop-test-publication.json"
Get-FileHash -Algorithm SHA256 .\validation\python-tests-v053.txt
```

The default packaged self-test is offline; `--self-test-mtp` is the separate device-dependent diagnostic. The drop test opens a temporary UI and injects native messages; it does not certify a physical mouse gesture or perform a backup. Hardware reproduction additionally requires the setup in [arduino/README.md](arduino/README.md) and [TRANSFER_UI.md](TRANSFER_UI.md), a registered PC, and a stored recovery key. New runs should record their own date, environment, artifact hashes, and results.

## Windows 0.5.3: MIDI history and USB recovery — 2026-10-01

- Confirmed that the unified transfer UI did not update its archive tree after a successful MIDI transfer and started with an empty tree on each launch. Signed commit receipts already existed locally. The Android store was intact.
- Added offline history from pinned-device signature-verified MIDI commit receipts and the last signed USB listing. Existing 0.5.2 MIDI receipts are supported. Display hints cannot override signed archive ID, size or hash. Incomplete, tampered, foreign-key and wrong-device receipts do not become successful history rows. A newer USB listing supersedes older receipts, including versions deleted on the phone.
- MIDI completion now refreshes the tree. USB backup completion requests a fresh listing. The recovery tab includes USB reconnection instructions, a recovery-key selector and a source/status column distinguishing cached USB history from MIDI commit records. No MIDI list/export/key-recovery API was added. Android remains 0.5.0.
- **90 Python tests passed**, including real Tk event-queue tests for successful transfer-to-history, restart persistence and no successful row on a failed transfer. Each Tk lifecycle case runs in a separate process. Initial test attempts encountered existing pytest cache/temporary-directory access errors and an in-process Tcl lifecycle error; the final run used a fresh test directory, disabled pytest caching and isolated Tk processes.
- Packaged 0.5.3 EXE offline runtime self-test passed; the 53-message asynchronous native drag-and-drop regression passed.
- On the normal C71 app, enabled MTP after the user unlocked the phone and started USB reception. The pinned-device signed listing returned **10 archives**. Retrieved the previously MIDI-committed 11,838-byte archive with ciphertext SHA-256 `f5ce1daa3d833e0501c5c6acfb82289de870fa257f5a568e41d8ea5e751e9768`; restored its Word document to a new work directory and verified SHA-256 equality with the current original. Existing source files and phone backups were not overwritten or deleted.
- The packaged 0.5.3 recovery tab displayed the cached history and successfully refreshed it from C71 over USB. This corrects the PC display/workflow defect; the serial transport remains an ingestion and ACK/status path.
- The previously MIDI-saved 2026-09-30 14:55 version was selected in the packaged 0.5.3 UI and its restore dialog opened. After desktop automation was interrupted by minimized-window/user-input detection, the user selected the destination and reported completion. This user-confirmed UI restore complements the independently hash-verified USB restore above; no additional hash comparison of the user's chosen output directory is claimed.

Evidence: `validation/python-tests-v053.txt`, `validation/exe-self-test-v053.json`, `validation/exe-drop-v053.json`, `validation/midi-usb-restore-v053.json`. Restored documents and recovery keys are excluded from the distribution.

## MIDI physical-link troubleshooting — 2026-09-30

- PC 0.5.2 stopped at frame 0 awaiting a signed ACK. The C71 development receiver showed zero received bytes and `USB get_status request failed`. The installed normal app was still 0.4.0. With the user's explicit approval, the normal app was updated in place to 0.5.0; no uninstall or data reset was performed.
- R3 was still sending diagnostic data. Both boards were updated to bridge firmware: R3 A on COM4, R4 WiFi B on COM5.
- The tested breadboard circuit uses two **PS817C optocouplers**, identified by package markings: one for data and one for ACK/status, each with two 330-ohm LED resistors in series (660 ohms) and a 2-kilohm output pull-up. On this circuit, 31250-baud tests lost or corrupted bytes in both directions, including with 2 ms spacing between USB input bytes. **Standard MIDI wire-speed operation remains unverified.** No oscilloscope measurement identifies the exact electrical cause; this result does not establish the PS817C's intrinsic speed limit.
- The bridges now collect bounded complete SysEx frames before UART transmission. This prevents software-serial transmission from competing with reception of the same USB frame. Both boards were built and uploaded with `C71_UART_BAUD=9600`; USB serial remains 115200. This is a development UART speed using MIDI SysEx encoding, not a compliant 31250-baud MIDI physical link.
- Actual R3-to-R4 and R4-to-R3 tests passed for generated 18-byte, 1 KiB and 64 KiB payload streams. The 64 KiB stream occupied 80,559 wire bytes, all received, with matching SHA-256 `a911553afe8127143c47c8f66b322e1837f8b946bf1ffc57dbe529d3d478e810` in each direction. These hashes cover the encoded wire stream.
- A 2,292-byte return frame supplied to R4 as a USB burst passed, exercising a reply larger than the board's serial input buffer. Oversized and incomplete forward-frame recovery tests also passed. Both boards were USB-connected to the same PC: **these are data-path tests, not proof of galvanic isolation or C71 commit.**
- Normal and development apps were monitoring the same MTP folder. A development-signed response failed the normal app's pinned signature verification. The development app was stopped, the normal receiver restarted, and normal device identity verification succeeded. The development app's launcher and screen titles now identify it as `開発版`; its rebuilt APK was installed and left stopped.
- After the user's authentication in the normal app, a fresh MTP escrow request returned `custody_verified=true` under the pinned normal-device signature. The selected recovery key is confirmed stored in the normal C71 app. No key material is included in the evidence or distribution.
- **The complete PC UI → R3 → optocouplers → R4 → OTG → normal C71 save/commit test passed.** The user connected R4 to C71, confirmed `USBシリアル接続・受信中`, and pressed the PC 0.5.2 transfer button for the selected Word test document. A new persisted MIDI receipt reported `type=4`, `sequence=25`, `code=committed`, `bytes=11838`, and SHA-256 `f5ce1daa3d833e0501c5c6acfb82289de870fa257f5a568e41d8ea5e751e9768`. The PC sender validates the session, sequence, expected encrypted size and hash before persisting this receipt. An independent read of the saved receipt also verified its ECDSA signature against the pinned normal C71 identity. The C71 commit path requires storage and read-back SHA-256 verification before this ACK.
- The recorded transfer used the two optocoupler paths at 9600 baud; R3 remained on PC USB and R4 was moved to C71 OTG. The user subsequently clarified that hardware transfers had already been tested repeatedly. The 11,838-byte receipt is one individually documented result, not a count of all tests performed. No aggregate duration, volume or throughput figures are assigned to the additional tests here. The MIDI path is for backup ingestion and signed ACK/status; restoration uses USB/MTP. The final Windows screen could not be captured by the UI automation tool, which repeatedly reported a minimized window/user input; this recorded success is established by the signed commit receipt rather than a claimed screenshot.

Evidence: `validation/framed-link-small-results.json`, `validation/framed-link-64k-results.json`, `validation/midi-link-31250-block1.json`, `validation/midi-link-31250-block16.json`, `validation/normal-midi-commit-result.json` (sanitized verification result; the signed original remains in the user's local PC receipt store). Bridge A build: 3,380 bytes flash / 947 bytes globals; bridge B R4 build: 52,080 bytes flash / 10,844 bytes globals. Android debug label build succeeded.

## Windows 0.5.2: isolate development diagnostics from USB readiness — 2026-09-30

- The reported `app.py` line 239 exception came from the explicit `--self-test` branch launched during 0.5.1 validation. That branch unconditionally constructed `MtpBridge` and left its exception uncaught. The regular application entry point did not invoke this test.
- `--self-test <output.json>` now tests GUI initialization, encryption/restore, monochrome QR and four-color QR without accessing USB. `--self-test-mtp <output.json>` explicitly adds read-only MTP discovery. Diagnostic failures write a structured JSON result, close the diagnostic UI and return a nonzero exit code; they do not produce an unhandled-exception dialog or claim success.
- **80 Python tests passed**, including no USB access in default diagnostics, a simulated missing-device error, and rejection of invalid device metadata.
- **Packaged EXE offline self-test passed**, exit code 0, with `mtp.status=not_requested`.
- **Packaged EXE explicit MTP test reproduced the unavailable-transfer-folder condition** and wrote `status=failed`, `phase=mtp`, the Japanese error message, and exit code 1. This is successful error handling, not successful USB communication. No C71 unlock, transfer, key operation or app installation was performed.
- **Packaged EXE drop regression passed again**, 53 asynchronous native drop messages, preserving the 0.5.1 fix.
- Android APK remains 0.5.0. The normal installed Android package was not updated by this fix.

Evidence: `validation/python-tests-v052.txt`, `validation/exe-self-test-v052.json`, `validation/exe-mtp-test-v052.json`, `validation/exe-drop-v052.json`.

## Windows 0.5.1: drag-and-drop crash fix — 2026-09-30

- Confirmed the reported Windows Application Error at 13:52:47: `C71Vault.exe`, `ucrtbase.dll`, exception `0xc0000409` (fatal application exit).
- Reproduced with the original drop handler by posting `WM_DROPFILES` asynchronously while Tk's `mainloop()` was running. Python aborted with `PyEval_RestoreThread ... the current Python thread state is NULL`. The same reproducer completed after the fix.
- Cause: the native window procedure called `root.after_idle()`. Calling Tk from that native callback can re-enter Tcl while its Python thread state is released. The handler now only collects paths into a queue and releases the drop handle. A normal Tk timer consumes the queue and updates the UI. Closing restores the window procedure and cancels the timer.
- The earlier 0.5.0 smoke test used synchronous `SendMessageW` from Python outside `mainloop()`. It did not exercise the failing dispatch context. That test has been replaced with asynchronous `PostMessageW` under the real event loop.
- **Source UI and packaged 0.5.1 EXE both passed 53 native drop messages**: Japanese/space-containing filenames, multiple files plus a folder, 50 repeated drops with duplicate suppression, ignoring additions while busy, clearing then dropping again, and clean/idempotent shutdown. USB/optical/MIDI option panels remained functional.
- Python regression suite: **77 passed** with warnings treated as errors.
- Windows UI inspection confirmed the packaged 0.5.1 window opened. An attempted Explorer mouse drag was blocked by the automation tool because it disallows a drag ending over a different application. **No successful physical mouse gesture is claimed here**; the asynchronous native-message regression above is the verified drop test.
- The additional combined EXE runtime self-test reached MTP discovery and exited with code 1 because the C71 transfer folder was unavailable. A source run identified the same MTP readiness error. Its preceding encryption/restore and QR checks completed; a new successful full MTP runtime result is not claimed. No backup transfer or user-key operation was performed in this fix.
- Android remains 0.5.0 in the distribution; this PC-only fix does not install or change the normal C71 package. Previous physical-transport limitations below remain applicable.

Evidence: `validation/drop-crash-before-v051.txt`, `validation/drop-crash-after-v051.txt`, `validation/ui-smoke-v051.json`, `validation/exe-drop-v051.json`, `validation/python-tests-v051.txt`.

To run the packaged drop regression: `C71Vault.exe --drop-self-test <absolute-output-json-path>`. It creates generated selection fixtures, opens a test UI, processes native messages, then exits without transferring data.

## 0.5.0 unified transfer UI — 2026-09-30

- Python regression and new selection/receipt/sender tests: **77 passed**.
- Android instrumentation on the connected C71, **development package only**: **64 passed**. Includes existing crypto/store/retention/optical/MIDI tests, local-folder persistence, signed receipt semantics, and signed START-v2 labels.
- Native Windows GUI integration: Unicode/space-containing multi-file `WM_DROPFILES`, duplicate suppression, refusal to add during transfer, remove/clear selection, and USB/optical/MIDI option panels passed. This test creates its own GUI process and generated files; it does not send user files.
- Windows screen inspection confirmed the main transfer screen, MIDI COM-port selector, and file-picker opening. An Explorer mouse-drag gesture was not independently recorded; the native drop message handler was exercised by the integration test.
- C71 development UI: created and selected `UI-Test` in private-storage folder categories. Main receive selector and start/stop controls displayed correctly.
- Android release/debug builds succeeded; release lint has no errors. Existing warnings remain in the report.
- ACK-enabled Arduino bridge compilation: UNO R3 3,112 bytes flash / 301 bytes globals; UNO R4 WiFi 51,920 bytes flash / 6,740 bytes globals.
- **Not yet verified:** the newly wired PS817C optocoupler circuit at 31,250 baud, end-to-end physical MIDI ACK, and a complete transfer through each newly integrated UI mode. Earlier transport validations below remain evidence for those earlier versions only.
- The signed 0.5.0 update APK is provided. The normal package has not yet been updated; normal-package migration is not included in these results.

Evidence: `validation/python-tests-v050.txt`, `validation/android-tests-v050.txt`, `validation/ui-smoke-v050.json`, `validation/android-ui-v050.png`, and Arduino build logs.

- Packaged Windows EXE self-test passed: GUI initialization, encrypted roundtrip, monochrome QR, four-color binary QR, OpenCV load and read-only MTP device discovery. Evidence: `validation/exe-self-test-v050.json`.


## 0.4.0：MIDI SysEx受信・暗号化バックアップ保存

### 自動テストとビルド

- Windowsテスト67件（従来62件＋MIDI5件）、C71上のAndroidテスト60件（従来33件＋MIDI27件）、計127件成功。
- MIDIでは正常・7-bit化・リアルタイムメッセージ混在、CRC不一致、不正length、上限超過、sequence欠落、同一/異なる内容の重複、未知type、途中切断、容量上限、SHA-256不一致、既存保管領域の内容保持を確認。容量試験は第1段階の受信上限であり、保存時のディスク不足試験ではありません。
- 保存モードでは未登録PC・署名改変・鍵未保管の拒否、保存quota・空き容量reserve不足、途中切断とCRC不一致時のstaging削除、SHA不一致・不正アーカイブヘッダー・staging改変の拒否、同一END/全転送の再送、旧版保持を追加検証。空き容量不足はreserve値を注入して再現し、実機のストレージを埋める試験は行っていません。
- ReleaseビルドとLint成功、Lintエラーなし。非致命的警告あり。
- 通常版APKにはDevelopmentSerialPipeクラスを含めず、INTERNET権限も追加していません。PC中継用ソケットは開発版だけです。
- UNO R3（AVR core 1.8.8）とUNO R4 WiFi（Renesas core 1.6.0）で、MidiTestSender/MidiBridgeA/MidiBridgeBの3スケッチをビルド。まず両実機へMidiTestSenderを書き込み、保存試験ではR3だけを生成データ専用MidiArchiveTestへ更新しました。現在R3は暗号化試験版の再送、R4は診断データ送信の状態です。橋渡し用MidiBridgeA/Bの実配線試験は未実施です。

### 実機：Arduino → PC中継 → C71

PCでC71（ADB端末ID末尾8618）、UNO R3（COM4、2341:0043）、UNO R4 WiFi（COM5、2341:1002）を確認。C71とR3はPCの同じハブ、R4は別USBポートという利用者の接続構成で開発しました。

両Arduinoが実際に生成したMIDI SysExを、USBシリアル→PC→ADBの開発用受信口へ中継しました。送信側の固定ハッシュとC71計算値を比較しています。

| 試験データ | R3 → C71 | R4 WiFi → C71 |
|---|---|---|
| C71VAULT MIDI TEST、18 bytes | CRC/SHA-256一致 | CRC/SHA-256一致 |
| 1,024 bytes、疑似乱数列 | CRC/SHA-256一致 | CRC/SHA-256一致 |
| 65,536 bytes、疑似乱数列 | CRC/SHA-256一致、END sequence 513 | CRC/SHA-256一致、END sequence 513 |

両試験ともエラー0件、CRC一致530フレーム、回線受信98,869 bytes。C71の実受信・計算を確認した結果ですが、**PC/ADB中継を含むためUSB Host直結・物理絶縁・31,250 baudのArduino間UART通信の検証ではありません。**

証跡：`validation/midi-r3-relay-v040.json`、`validation/midi-r4-relay-v040.json`、`validation/android-tests-v040.txt`、`validation/python-tests-v040.xml`。

### 実機：R4 → C71 USB Host直結

通常版APKでR4を `UNO WiFi R4 CMSIS-DAP [2341:1002] / CdcAcmSerialDriver #0` として検出。PCから外したC71にOTGで直接つなぎ、18 bytes・1,024 bytes・65,536 bytesを4周受信しました。全2,120フレームでエラー0、全SHA-256がPCの期待値と一致しました。64KBはEND sequence 513まで到達しています。初回は64KBの途中で切断され、未完了と表示されたことも確認しました。

証跡：`validation/midi-r4-otg-v040.json`。USB CDC部分は115200 baud設定です。PC/ADBは転送経路に含まず、ログ取得はPCへ戻した後です。

### 実機：R3 → C71でバックアップ保存 → PCで復元

通常版APKでR3を `[2341:0043] / CdcAcmSerialDriver #0` として検出。登録済みの試験PC鍵で署名したSTARTと、生成した2ファイルから作った**暗号化済み1,900 bytes**を、R3→C71 OTG直結でSysEx送信しました。

- sequence 5、CRC一致7フレーム、エラー0。
- C71ログで保存後SHA-256と `committed=true` を確認。
- C71をPCへ戻して既存USB/MTP経路から取得。署名付き取得応答と暗号文SHA-256を確認。
- 以前C71から回収した試験用復元鍵で、2ファイル・平文1,081 bytesを復元。両ファイルが元データと一致。

証跡：`validation/midi-backup-restore-v040.json`。ユーザーの実文書・新しい復元鍵は使用していません。試験版1件はC71に残しています。必要なら既存の端末認証付き削除で整理できます。

### 未検証の範囲

USB MIDIクラスの実機入力、フォトカプラ配線、31,250 baudのArduino間UART実配線、大容量のMIDIバックアップ、電源断の全タイミングは未検証です。USBシリアル上のMIDI 1.0 SysExを確認した結果であり、電気的なMIDIインターフェースや物理絶縁の完成を意味しません。

## 0.3.1：光学画面の上下配置

- 白黒・4色ともACKコードを上段、前面カメラ映像を下段に変更。
- 同じ証明書で署名した更新APKをC71に上書き導入し、両画面の実際の表示座標から配置を確認。4色受付はスクリーンショットでも表示を確認し、ACKコードを復号できることを確認。
- Releaseビルド成功、Lintエラーなし。証跡：`validation/layout-v031.json`。
- 今回の変更は画面配置・案内・バージョン表示のみ。転送の実機試験結果は下記0.3.0の記録であり、0.3.1での再転送試験は行っていません。

## 0.3.0：4色・バイナリ・まとめACK

- Windows自動テスト62件、Android実機上の自動テスト33件、計95件成功。
- 配布用Windows EXEでもGUI生成、暗号化・復元、白黒QRと4色バイナリの生成・復号、OpenCV読み込み、MTPでのC71認識を確認（`validation/windows-exe-self-test-v030.json`）。
- 4色画像の2層からバイナリ全値を復号。減光・色偏り・ぼかし・回転・台形変形を加えた画像、Android NV21の色差間引きを含む人工画像を検証。
- パケットの署名、改変・異なる画面の色層混合・別セッション・別転送の拒否、8枚内の順不同、重複、欠落した番号だけの再送、古いACKの識別を検証。
- 復元鍵保管と容量制限を確認し、END以前は保管領域に確定しないことを検証。従来の白黒光学・USB・保持ルールのテストも成功。

### 画面とカメラによる実機試験

C71（RMX5303）の前面カメラとPC画面、C71画面とPCカメラを使用し、**暗号化後13,208バイトを、最大1,024バイト×13データ画面**で保存しました。8枚と5枚の受信窓を使い、署名付き最終ACKと保存ハッシュを確認しました。USBは光学試験中のデータ経路には使用していません。

その後USBで取得し、以前C71から回収した試験用復元鍵で2ファイル（平文12,346バイト）を復元しました。全ファイルのSHA-256が元データと一致しています。別途登録済みのPC認証情報で取り出しました。

初期の720×720カメラ映像では読み取りが進まず、高解像度を優先する設定に変更しました。成功時のC71映像は1920×1080、データ画面の表示時間は1秒です。小さい制御パケットは低密度のQRにし、必要時には読めた色層の位置情報をもう一方にも使います。

開始から最終ACKまで約170秒かかりました。この時間には位置合わせ、読取り待ち、再送が含まれます。純粋な転送速度や従来方式に対する倍率の測定ではありません。**多MiBの実用速度・安定性は未検証です。** 16MiBは入力上限であり、性能保証ではありません。

証跡：`validation/python-tests-v030.xml`、`validation/android-tests-v030.txt`、`validation/color-optical-and-restore-v030.json`。試験には生成データだけを使用しました。

## 0.2.0の追加検証

- Windows自動テスト **36件成功**。RSA鍵カプセル、別PCの一時鍵への回収、異なる鍵の拒否、光学フレームの署名と復元、固定長ACK以外の拒否、320/480/700ピクセル内にQR全体と余白が収まって復号できることを検証。
- C71上のAndroid自動テスト **23件成功**。直近30日、31日/180日、週の月曜、1年、月別、対象別、未来日時、重要指定、最新版、旧形式保護、15%境界、整理実行直前の再判定を検証。光学は欠落・順序逆転・改変・セッション違い・重複を検証し、最終フレームまで保存を確定しないことと、逆方向のexport/recover_key/list/delete拒否を確認。
- C71実機で、利用者の端末認証による試験用復元鍵の保管が成功。
- 初期化後を模した**別のPC認証情報**を新規登録し、再度の端末認証で復元鍵を回収。元の鍵との完全一致を確認。既存PCの署名用秘密鍵は回収に使用していません。
- 同じAPK署名で0.1から更新し、C71の端末署名鍵・登録・転送フォルダ設定を維持。
- Lintエラーなし。非致命的な警告は残っています。
- 更新版APKの権限はForeground Service、Special Use、通知、Wake Lock、Cameraのみ。INTERNET権限なし。
- 更新版Windows EXE自身でGUI生成・暗号化復元・MTP認識が成功。
- 最終EXEでQR生成・復号、OpenCVモジュールの読み込みも成功。USBデバッグOFFに戻した後も、MTPの端末署名・署名付き一覧と光学保存版の存在を確認（`validation/protected-mode-v020.json`）。

証跡: `validation/python-tests-v020.xml`、`validation/android-tests-v020.txt`、`validation/windows-exe-self-test-v020.json`。光学のカメラ実機試験の状況は下の追記に記載します。

### 光学から新しいPCへの復元まで（実機）

PC画面とC71前面カメラ、C71画面とPCカメラを実際に向かい合わせて、暗号化ファイル **1,963 bytes / 全6フレーム**を送信しました。USBは光学試験中のデータ経路には使用していません。最終ACKの署名・保存ハッシュを確認しました。

その後、初期化後を模した新しいPC認証情報でUSBから暗号化ファイルを取得し、**C71から回収した鍵**で2ファイル（平文1,095 bytes）を復元しました。全ファイルが元データのSHA-256と一致しています。証跡は `validation/optical-and-recovery-v020.json` です。

最初の固定サイズQRはウィンドウ内で切れる問題があり、全体と余白が収まる整数倍表示に修正しました。戻りACKも固定長の小さな形式に変更しています。位置合わせの影響が大きく、少量でも待ち時間が発生しました。**多MiBの光学転送速度・安定性は未検証です。** 上限16MiBは入力制限であり、実用速度の保証ではありません。

試験に作成した「光学実機試験・生成データ」1版をC71に残しています。利用者の実文書ではありません。不要ならC71の個別削除で端末認証して削除できます。

## 0.1.0での検証記録

## 実行した試験

| 試験 | 結果 |
|---|---|
| Windows側の自動テスト | 24件成功 |
| C71上のAndroid自動テスト | 9件成功 |
| Android配布版のビルド・Lint | 成功、Lintエラーなし。非致命的警告あり |
| APK署名検証 | v3署名の検証成功 |
| 配布APKの開発アクセス禁止 | `run-as` は package not debuggable として拒否 |
| Windows配布EXE | GUI生成、暗号化復元、MTPでのC71公開情報取得に成功 |
| 実機USB保存・復元 | 開発版・配布版の双方で成功 |
| USBデバッグOFFでの接続 | ADB接続が消えたことと、MTPで端末署名・署名付き保存一覧を取得できることを確認 |

## 配布APKのUSB試験

生成した32MiBの乱数ファイル、日本語文書、空ファイル・空フォルダを使用しました。ユーザーの実ファイルは使用していません。

- 暗号化サイズ: **33,566,110 bytes**
- 保存要求・USB転送・端末での読み戻し確認: **1.70秒**
- 復元用書き出し・USB受信: **3.83秒**
- 全3ファイルのSHA-256が元データと一致。
- PCの元文書を上書きした後も、保存した旧版の暗号文が変化していないことを確認。
- `delete / overwrite / clear / prune` の各要求は拒否。
- 同じ保存IDで内容を変更する要求は拒否。
- 未登録PCからの要求は拒否。
- 拒否試験後も、保存済みの版を再取得してハッシュ一致を確認。

計時に最初のPC側暗号化時間は含みません。この小さな試験から、多GiBの速度・安定性は推定していません。データ転送はWindows MTPとAndroid SAFのみを使用しました。ADBはインストールと端末操作・テスト起動に使用しました。

## 自動テストの範囲

Windows: 日本語名・バイナリ・空ファイル・空フォルダ・更新時刻の復元、暗号の乱数性、別鍵・改変・切断の拒否、安全でないパス、既存出力の保護、鍵の作成・読み戻し、元データ変更検出、読取不能フォルダを成功扱いしないこと、認証済みでも危険なZIPの拒否、DPAPI鍵の再読取、端末鍵の変更拒否、署名応答の改変拒否。

Android: 保存後の読み戻しと再送、上書き拒否、途中切断・ハッシュ不一致の拒否、容量上限で旧版を保持、空き容量確保、パストラバーサル拒否、署名応答、入力ストリームの故障で未確定データを残さないこと。

## 未検証の範囲

長時間・多GiBの連続運用、USB物理抜去・電源断の全タイミング、ストレージ物理故障、悪意あるAndroid OS、全Windows/Android機種への互換性、第三者による侵入試験は未実施です。端末PINを入力して行う削除の完了試験は行っていません。

本結果は企業向け認証や完全なランサムウェア耐性の保証ではありません。[SECURITY.md](SECURITY.md) の前提と併せて使用してください。

## 証跡

- `validation/python-tests.xml`
- `validation/android-tests.txt`
- `validation/release-mtp-roundtrip.json`
- `validation/debug-mtp-roundtrip.json`
- `validation/windows-exe-self-test.json`
- `validation/android-lint.html`
- `validation/mtp-protected-mode.json`

試験用の復元鍵、DPAPI秘密情報、APK署名用秘密鍵は配布物には含めていません。

配布版の試験後、生成したデータだけを初期化して、転送フォルダとこのPCを再登録しています。このため、試験記録の端末署名鍵と引渡し時の端末署名鍵は異なります。引渡し時の値は `mtp-protected-mode.json` に記録しています。
