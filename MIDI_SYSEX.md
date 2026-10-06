# MIDI / isolated reception — C71 Vault 0.4.0

The wire format is **MIDI 1.0 System Exclusive (SysEx)**. No Note On/Off encoding
is used. Inter-board UART is configured for **31,250 baud, 8N1**. The current
Arduino USB serial adapter uses **115,200 baud**; this is a separate hop.
Native USB MIDI does not use a UART baud setting.

The Android screen enumerates USB Host devices and serial ports without an
application-specific VID/PID whitelist. It also lists USB MIDI output ports via
Android `MidiManager`. UNO R3 and the detected UNO R4 WiFi normally enumerate
as USB CDC serial devices, not USB MIDI devices. Their CDC test transports
carry the exact SysEx byte stream; they do not establish USB MIDI-class support.

## Current scope

The receiver accepts HELLO, START, DATA, END and ABORT. Diagnostic transfers
validate CRC, sequence, total size and SHA-256 without saving their content.
The maximum diagnostic transfer is 1 MiB. Authenticated backup transfers accept
encrypted `.c71b` archives up to 16 MiB, stage them, validate them, and reuse the
existing vault readback and atomic commit. DATA is processed incrementally.
This transport cannot list, export, delete or change existing backups, retrieve
or register recovery keys, change retention, or execute commands.

The existing USB/MTP, optical, recovery and retention paths remain separate.
Opening this screen stops USB/MTP reception; leaving it stops this receiver.
Normal operation still requires ADB disabled. The release APK has no development
relay implementation and requests no INTERNET permission.

## MIDI framing

```
F0 7D 43 37 31 <7-bit packed raw frame> F7
```

`7D` is the non-commercial/development SysEx ID. `43 37 31` is this experiment's
`C71` namespace, not an assigned manufacturer ID. This experimental ID must be
replaced with an appropriate registered ID before a commercial/public MIDI
product release. This is not a claim of MIDI certification or an electrical
MIDI interface: the optocoupler/current-loop hardware has not been implemented.

Group raw bytes in blocks of up to seven. Output a high-bit mask first:
bit i is bit 7 of raw byte i. Output each byte's low seven bits after it.
An incomplete final group has zero in unused mask bits. All bytes between F0
and F7 are consequently below 0x80. Real-time bytes F8–FF may be interleaved
and are ignored by this file receiver. Other status bytes interrupt the SysEx
and invalidate an active transfer. Each new F0 restores framing.

Raw frame, all multibyte integers big-endian:

| Offset | Bytes | Field |
|---|---:|---|
| 0 | 4 | ASCII `C7IS` |
| 4 | 1 | Version 1 |
| 5 | 1 | Type: HELLO=1, START=2, DATA=3, END=4, ABORT=5 |
| 6 | 16 | Nonzero session ID |
| 22 | 4 | Unsigned sequence |
| 26 | 2 | Payload length, at most 512 |
| 28 | 0–512 | Payload |
| last 4 | 4 | CRC-32/ISO-HDLC of all preceding raw bytes |

CRC uses reflected polynomial ED B8 83 20, initial FFFFFFFF and final XOR
FFFFFFFF (same as Python zlib.crc32). Raw maximum: 544 bytes. Complete SysEx
maximum: 628 bytes. The parser never buffers beyond this bound.

- HELLO: sequence 0, no payload; must precede START for that session.
- Diagnostic START: sequence 0; uint64 expected length + 32-byte SHA-256 (40 bytes). No name or path.
- DATA: sequence starts at 1, increases by one; nonempty payload.
- END: next sequence, empty payload. Success requires exact size and hash.
- ABORT: current session, empty payload; discards current diagnostic state.

An identical START or most recently accepted DATA/END may be retransmitted
without counting bytes twice. Conflicting duplicates, missing/outdated
sequences, wrong sessions, length/CRC/hash errors and disconnect before END
invalidate the transfer. Start again with HELLO and a new session. No ACK is
required, so a future one-way physical path can use the same input format.

CRC and SHA are integrity checks, not sender authentication. Diagnostic mode
has no commit capability. Backup mode additionally requires the following
signed START and an already registered PC identity and escrowed recovery key.

## Authenticated backup START

The START payload is distinct from the 40-byte diagnostic payload:

| Offset | Bytes | Field |
|---|---:|---|
| 0 | 1 | Backup subformat 1 |
| 1 | 8 | Ciphertext archive length, uint64 |
| 9 | 32 | Ciphertext SHA-256 |
| 41 | 32 | Registered PC public-key fingerprint |
| 73 | 16 | Recovery key ID, lowercase ASCII hex |
| 89 | 16 | Series ID |
| 105 | 1 | DER ECDSA signature length, 8–72 |
| 106 | variable | SHA256withECDSA signature |

The signature covers ASCII `C71-MIDI-START1`, followed by the 16-byte session
ID and payload bytes 0–104. The session ID becomes a fixed-width hexadecimal
archive ID. File paths and labels are never supplied by the sender; the local
label is `MIDIバックアップ`. This binds size, hash, series and recovery-key ID
to the registered PC. Initial PC pairing and key escrow use existing USB UI.

Before staging, capacity must accommodate both staging and pending vault data
while keeping the existing free-space reserve. END requires the expected size
and SHA-256. The app fsyncs staging, reads it back and hashes it, then invokes
`Vault.store`, which validates the encrypted header, writes app-private pending
data, reads it back, and atomically commits it. Existing-ID retries also verify
the stored bytes. Only then does the UI show `commit済み`. A failed/disconnected
incomplete transfer discards its staging file and does not delete old backups.
Unexpected process death may leave an uncommitted staging file; that file is
never treated as a saved archive.

There is no production return-data channel in this implementation. Check C71's
commit display; a PC serial write or a generated `.syx` file is not a storage
receipt. The sender prints `sent_unconfirmed`, not success.

### Windows sender

Extract `C71Vault-source.zip` for the Python sources. The existing desktop EXE
is unchanged; the initial MIDI sender is a CLI:

```
python desktop/midi_send.py encrypted.c71b --output prepared.syx
python desktop/midi_send.py encrypted.c71b --port COM4
```

Use the existing registered PC identity (`--state` overrides its directory),
and install the desktop requirements plus `requirements-midi-dev.txt`. `--port`
expects Arduino A running MidiBridgeA and uses conservative UART pacing. The
two-board UART wiring is not yet physically tested. A `.syx` file contains
ciphertext and a signature, never the recovery key or PC private key.

## Hardware tests

`arduino/MidiTestSender` builds for UNO R3 and UNO R4 WiFi. It emits the phrase
`C71VAULT MIDI TEST`, 1 KiB and 64 KiB of reproducible pseudo-random data. It
repeats, allowing the phone receiver to be opened after a cable change.
`arduino/midi-fixtures.json` records independently calculated SHA-256 values.

While all devices connect to the PC, `desktop/midi_dev_relay.py` can relay a
physical Arduino COM port to the debug APK's local ADB socket. This validates
Arduino-generated bytes and C71 decoding; **it does not validate Android USB
Host or isolation**. The normal release does not contain the relay class.

For USB Host verification, disconnect C71 from the PC, connect UNO through
USB-C OTG, open MIDI/絶縁通信受付, select its device/port, leave USB baud at
115200, and tap 受信開始. Approve Android's USB access dialog. Actual outcomes
belong in VALIDATION.md; supported driver families are not proof of hardware
success. R4 direct diagnostic reception and R3 direct authenticated archive
ingestion/restoration were physically verified; see VALIDATION.md for sizes
and limitations. Native USB MIDI-class input remains untested on hardware.

## Dependencies and references

- [usb-serial-for-android v3.10.0](https://github.com/mik3y/usb-serial-for-android/tree/v3.10.0), MIT. Main Java sources are vendored unchanged; the Gradle wrapper module is adapted to this project's toolchain. CDC/ACM is detected by interface class; drivers also cover CH340/341, FTDI, CP210x and PL2303. Not every device or arbitrary baud rate is guaranteed.
- [Android USB Host](https://developer.android.com/develop/connectivity/usb/host)
- [Android MIDI API](https://developer.android.com/reference/android/media/midi/package-summary)
- [MIDI 1.0 message summary](https://midi.org/summary-of-midi-1-0-messages)
- [MIDI Association SysEx ID policy](https://midi.org/new-midi-association-sysex-id-policies-as-of-oct-15-2025)


## 0.5.0 return channel and START version 2

The upload frame types remain HELLO/START/DATA/END/ABORT. START body version 1 is still accepted. Version 2 keeps the first 105 body bytes (with version byte 2), appends a big-endian u16 UTF-8 label length and 1–300 label bytes, then the existing u8 DER-signature length and signature. The label is limited to 100 UTF-16 code units and may not contain control characters. The signature covers the unchanged `C71-MIDI-START1` domain, session, and the entire extended body. No remote path or folder field is introduced.

Replies use `F0 7D 43 37 41 [7-bit-packed UTF-8 JSON envelope] F7` (`C7A`). The envelope has base64 payload and ECDSA signature, using the pinned C71 receipt key. Payload fields are protocol=`C71-MIDI-ACK1`, device, session (32 hex), type, sequence, code, bytes. Codes are ack, error, verified (diagnostic only), or committed. Only committed includes sha256. No arbitrary error text, files, keys, history or paths are returned. The PC parser caps a reply at 4096 encoded bytes.

The GUI sender uses stop-and-wait because UNO R3 SoftwareSerial cannot send and receive simultaneously. Each frame is paced in 16-byte USB writes, then waits for a signed, matching ACK, retrying the identical frame at most twice. Only a matching END/committed reply with correct size and SHA-256 is success. ACK loss can leave a committed phone backup with an unconfirmed PC result; no existing backup is deleted to resolve this. The standalone legacy `midi_send.py` remains send-only and explicitly reports sent_unconfirmed.

Bridge A now also routes isolated UART RX back to PC USB. Bridge B routes C71 USB ACK bytes to UART TX. A second optocoupler is required for the return channel. Physical isolation does not itself enforce ACK-only contents; the C71 reply encoder limits the response fields.
