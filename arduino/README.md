# MIDI stage-1 firmware

Targets: **Arduino UNO R3 and UNO R4**. The connected R4 was identified as
UNO R4 WiFi (2341:1002). No Nano is required.

| Sketch | Role | R3 MIDI pin | R4 MIDI pin |
|---|---|---|---|
| MidiTestSender | Generates three known SysEx test streams over USB serial | None | None |
| MidiBridgeA | USB serial input to MIDI UART output | SoftwareSerial TX D9 | Serial1 TX D1 |
| MidiBridgeB | MIDI UART input to USB serial output | SoftwareSerial RX D8 | Serial1 RX D0 |

USB serial is 115200 baud. Bridge UART defaults to 31250 baud, 8N1; override
`C71_UART_BAUD` in both builds together for experiments. No Note On/Off messages are used.
These sketches carry MIDI SysEx bytes over the stock USB CDC bridge. They do
not reflash the UNO R3 ATmega16U2 or R4 WiFi ESP32 USB bridge and do not claim
USB MIDI-class enumeration.

Test source needs no inter-board wire. It sends an 18-byte phrase, 1 KiB, and
64 KiB of deterministic pseudo-random bytes with independently computed SHA-256.
All payload byte values, including MIDI status values, are encoded to seven
bits inside SysEx. It waits five seconds, sends the three cases, and repeats
after fifteen seconds. Opening R3's USB port generally resets its main MCU.

The bridges collect a complete bounded SysEx frame before transmitting it to
UART. This avoids USB receive overruns while AVR SoftwareSerial is transmitting.
Role A allows 640 wire bytes; role B allows 4096 on R4 and 1152 on R3.
The tested arrangement is **R3 as A, R4 as B**. Large signed replies can exceed
the R3 role-B limit, so swapping the boards is not verified for backup ACKs.
Overflow, invalid status bytes and incomplete frames older than three seconds
discard the pending frame. A new F0 restores framing; real-time bytes are ignored.
Senders must wait for the reply before sending the next frame. There is no queue
for an entire file or for simultaneous continuous transmission in both directions.

The user's breadboard circuit uses two **PS817C optocouplers** (identified by
package markings), one for data and one for ACK/status. Each LED input uses
two 330-ohm resistors in series (660 ohms); each output uses a 2-kilohm pull-up.
This circuit was tested on 2026-09-30. At 31250 baud, bytes were lost or
corrupted; the exact electrical cause has not been measured. This is a result
for the tested circuit, not a determination of the PS817C's intrinsic speed limit.
Both boards currently use **9600 baud UART for development**, with MIDI SysEx
encoding and unchanged 115200 USB serial. This is not standard MIDI wire speed.
18-byte, 1 KiB and 64 KiB generated payload streams matched in both directions
at 9600 baud. See ../VALIDATION.md for scope and evidence.

For the isolated configuration, A and B grounds must not be joined; USB
connections to the same PC also bypass electrical isolation. The development
test with both boards connected to the PC establishes data transport only.
TTL pins alone are not a complete electrical MIDI current-loop interface.

Build examples (Arduino CLI; generated binaries are work products):

```
arduino-cli compile --fqbn arduino:avr:uno MidiTestSender
arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi MidiTestSender
arduino-cli compile --fqbn arduino:avr:uno --build-property "compiler.cpp.extra_flags=-DC71_UART_BAUD=9600" MidiBridgeA
arduino-cli compile --fqbn arduino:renesas_uno:unor4wifi --build-property "compiler.cpp.extra_flags=-DC71_UART_BAUD=9600" MidiBridgeB
```

Use the board actually selected by `arduino-cli board list`. Stage-1 outcomes,
including which sketches were uploaded, are recorded in ../VALIDATION.md.
