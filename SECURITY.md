# 保護の設計と限界

## 想定する状況

Windows側の誤操作やマルウェアから、C71に保存済みの版を削除・上書きされにくくする設計です。AndroidのOSとアプリ隔離、端末ロック、USBデバッグOFFを信頼の前提とします。認定されたWORM装置や、侵害されたAndroid OSに耐える保管装置ではありません。

## 実装した保護

- PCで暗号化し、C71には暗号化ファイルを保存します。256-bitのランダムな復元鍵から、バックアップごとにランダムな16-byte saltを用いてHKDF-SHA256で暗号鍵を導出します。AES-256-GCM、12-byte nonce、16-byte tagを使い、形式ヘッダーも認証対象です。
- 0.2では復元鍵の予備をC71にも保管します。PCがC71の公開鍵でRSA-2048 OAEP（SHA-256、MGF1-SHA1）暗号化し、C71は端末認証後に復号・鍵ID照合してから専用領域に保管します。USB受渡し領域に平文の復元鍵を置きません。既存の保管鍵をPC要求で上書きしません。
- C71の復元鍵用RSA秘密鍵はAndroid Keystoreに置き、デバイス資格情報での認証を要求します。Keystoreの有効期間は認証後30秒ですが、アプリの各保管・回収操作は毎回OSの認証画面を通します。回収はPCからの署名付き要求に加えてC71画面での操作が必要です。回収用の一時RSA公開鍵で包み直した鍵だけをUSBで返します。
- PC初期化後は、新しいPCの署名鍵をC71で登録し、事前保管した復元鍵を回収できます。鍵を作り直す機能ではありません。C71の故障やKeystore失効に備え、独立した安全な保管先にも鍵を保持してください。
- Windowsの署名用ECDSA P-256鍵は、そのWindowsユーザーのDPAPIで保護します。C71の署名用ECDSA鍵はAndroid Keystoreに置きます。ハードウェア保護の有無は保証しません。
- 初回はC71上でPC鍵の照合・登録が必要です。WindowsもC71の署名鍵を固定し、変化したら接続を拒否します。
- 受信データは一時ディレクトリに書き、宣言サイズとSHA-256を確認し、同期書き込み・全体の読み戻し検証後にアトミックな移動で確定します。
- 保存IDの再使用による内容変更を拒否します。容量不足を理由に旧版を自動削除しません。
- USBのPC向けAPIは登録・一覧・新規保存・書き出し・受渡しファイルの整理・暗号化鍵の保管/回収要求です。鍵の保管/回収はC71での認証待ちとなります。削除・上書き・全消去のAPIはありません。
- 文書の格納先はアプリ専用領域です。MTPで見える転送フォルダは受渡し用です。Androidクラウドバックアップと端末移行によるアプリデータ持ち出しを無効化しています。
- AndroidアプリにINTERNET権限、ストレージ全体へのアクセス権限はありません。利用者が選んだ `Documents/C71Vault` だけをSAFで読み書きします。
- 復元では全暗号文の認証を完了してからZIPを展開します。パストラバーサル、危険なWindows名、重複、リンク、過大な展開、目録との不一致を拒否し、新規フォルダに復元します。
- 保持ルールは対象識別子ごとに削除候補を計算するだけです。実行にはC71での候補確認と端末認証が必要です。実行時にも再計算し、重要指定済みの版を除外します。容量15%未満の警告から削除処理を実行しません。
- 光学受信は登録済みPCの署名、C71が生成したセッションID、連番、データ長、SHA-256を検証します。ACKはC71の署名付きで、固定の状態コード・ID・連番・バイト数・最終ハッシュだけを返します。光学から文書・復元鍵・一覧の書き出しを呼べません。PC側も想定外フィールド・状態コードを拒否します。

## 防げないこと・残る情報

- PCが侵害されている間は、PC上の平文と利用可能な復元鍵が盗まれる可能性があります。DPAPIは同じユーザーとして動くマルウェアを防ぎません。鍵ファイル `.c71key` 自体は平文JSONです。
- 登録済みPCは新規の無価値なデータを保存して容量を消費できます。転送フォルダへの妨害も可能です。可用性やサービス妨害への耐性は保証しません。
- USB接続した登録済みPCは全保存版の暗号文を取得できます。PC別の閲覧権限や管理者による登録解除のUIは本版にはありません。内容の閲覧には各版の復元鍵が必要で、C71からの鍵回収は端末認証で承認する必要があります。
- 署名付き応答は要求IDに結び付けますが、要求を恒久記録するリプレイ防止台帳はありません。同じ内容の保存は同じ版として扱われ、再送から削除・上書きはできません。リプレイによる処理負荷は防げません。
- C71のアンインストール・アプリデータ消去・端末初期化、root/OS侵害、物理破損、紛失には耐えません。画面ロックの無効化等で認証用Keystore鍵が失効した場合も鍵を回収できません。端末のUSBデバッグをONにすると、認証済みADB接続からアプリの消去が可能です。
- 保存名、容量、日時、保存ID、鍵ID、PC名、公開鍵等は暗号化しない管理情報です。文書名・内容の目録は暗号化ファイル内に入れます。PCの画面やローカルログには処理中の文書名が表示されます。
- 復元時にはPCに平文の一時ファイルを作ります。通常の削除は媒体上の完全消去を保証しません。PCのディスク暗号化等は別途必要です。
- バックアップはフォルダの順次読取りです。VSS、DBの整合性スナップショット、OS全体・ACL・代替データストリームの保全は実装していません。読取り権限エラー、読取り中に検出したサイズ/更新時刻等の変化は失敗にしますが、フォルダ全体が同一時点の状態であることは保証しません。
- 端末認証付き削除はアプリUIの保護です。暗号鍵を端末認証に結び付けたハードウェア消去制御ではありません。
- 光学の非対称性はアプリのプロトコルによる制限です。双方向にカメラと画面がある以上、侵害されたOSが別の情報を光に載せることまで阻止できません。物理的なデータダイオードの保証はしません。カメラ映像をファイルへ保存する機能はありません。

## 実機の条件

検証端末はrealme C71 / RMX5303、Android 15、読み取れたセキュリティパッチ日は2025-08-01です。この古いパッチ状態を含め、企業の正式なセキュリティ認証・第三者侵入試験は受けていません。多GiBでの耐久、実際の電源断、全OEM端末での動作は未検証です。

## 参照した仕様

- [Android Storage Access Framework](https://developer.android.com/training/data-storage/shared/documents-files)
- [Android Foreground service types](https://developer.android.com/develop/background-work/services/fgs/service-types)
- [Android Keystore authentication parameters](https://developer.android.com/reference/android/security/keystore/KeyGenParameterSpec.Builder#setUserAuthenticationParameters(int,%20int))
- [ZXing Android Embedded](https://github.com/journeyapps/zxing-android-embedded)
- [CISA Ransomware Guide](https://www.cisa.gov/stopransomware/ransomware-guide)

上記への準拠認証や製品保証を表すものではありません。


## 0.3：4色光学転送

4色方式もPC→C71の暗号化データと、C71→PCの署名付きACK・状態だけに限定します。バイナリ形式にしても各要求の署名は省略しません。2色層は同じ撮影フレームから復元し、パケット識別ハッシュとPC署名を検証します。セッション・転送ID・連番・長さも検証します。

最大8枚分をメモリに保持し、まとめACKで不足分を通知します。部分ACKは受信状況であり永続保存の証明ではありません。全8枚（最終組は残数）を揃えて同期書き込み後に完全ACKを返します。最終成功は全体のハッシュと既存の保存・読み戻し検証が通った場合だけです。POLLごとのトークンで古い部分ACKの混同を防ぎます。

光学受付画面ごとに新しいセッションを作ります。途中終了後の再開は未対応です。新方式もOS侵害に対する物理的な一方向通信保証はありません。仕様は [OPTICAL_V2.md](OPTICAL_V2.md) を参照してください。

## MIDI SysEx transport (0.4.0)

MIDI diagnostic messages only compute bounded CRC/SHA results. Backup START
messages additionally require the registered PC's ECDSA signature over session,
ciphertext size/hash, series and recovery-key ID, and existing phone key custody.
The transport has no list, export, key registration/recovery, delete, importance,
retention or arbitrary command API. Paths and archive labels are chosen locally.
Staging, size/hash verification, readback and the existing atomic Vault.store
commit are required before backup success. Old backups are never pruned here.

SysEx/CRC alone is not authentication or physical isolation. The optocoupler
and inter-board wiring are unfinished. USB serial test connections remain normal
USB connections. The development-only ADB relay is absent from release builds;
the normal policy of disabling ADB for protected operation is unchanged.
