// Role A: PC USB -> MIDI 1.0 SysEx bytes -> 31250 baud UART TX.
// Bounded SysEx buffering prevents SoftwareSerial TX from dropping USB RX bytes.
#include <Arduino.h>
#if defined(ARDUINO_AVR_UNO)
#include <SoftwareSerial.h>
SoftwareSerial midiUart(8,9); // UNO R3: isolated ACK RX D8; data TX D9.
#else
#define midiUart Serial1 // UNO R4: ACK RX D0; data TX D1.
#endif
const unsigned long USB_BAUD=115200;
#ifndef C71_UART_BAUD
#define C71_UART_BAUD 31250
#endif
const unsigned long MIDI_BAUD=C71_UART_BAUD;
// Largest C71 DATA frame: 544 raw bytes + 78 high-bit bytes + 6 envelope bytes.
const size_t FRAME_CAPACITY=640;
uint8_t txFrame[FRAME_CAPACITY];
size_t txLength=0;
unsigned long lastUsbByte=0;
void setup(){Serial.begin(USB_BAUD);midiUart.begin(MIDI_BAUD);}
// PC must wait for the signed C71 reply before sending another complete frame.
void loop(){
  if(txLength&&millis()-lastUsbByte>3000)txLength=0;
  if(midiUart.available())Serial.write((uint8_t)midiUart.read());
  while(Serial.available()){
    uint8_t b=(uint8_t)Serial.read();lastUsbByte=millis();
    if(b>=0xf8)continue; // MIDI real-time messages do not belong to SysEx.
    if(b==0xf0){txLength=0;txFrame[txLength++]=b;continue;}
    if(!txLength)continue;
    if((b>=0x80&&b!=0xf7)||txLength>=FRAME_CAPACITY){txLength=0;continue;}
    txFrame[txLength++]=b;
    if(b==0xf7){
      for(size_t i=0;i<txLength;i++)midiUart.write(txFrame[i]);
      txLength=0;
    }
  }
}
