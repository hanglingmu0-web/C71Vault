// Role B: 31250 baud MIDI UART RX -> USB serial -> C71 SysEx receiver.
// This sketch does not change the board's USB descriptors to USB MIDI class.
#include <Arduino.h>
#if defined(ARDUINO_AVR_UNO)
#include <SoftwareSerial.h>
SoftwareSerial midiUart(8,9); // UNO R3: data RX D8; ACK TX D9.
#define C71_REPLY_CAPACITY 1152
#else
#define midiUart Serial1 // UNO R4: data RX D0; ACK TX D1.
#define C71_REPLY_CAPACITY 4096
#endif
const unsigned long USB_BAUD=115200;
#ifndef C71_UART_BAUD
#define C71_UART_BAUD 31250
#endif
const unsigned long MIDI_BAUD=C71_UART_BAUD;
// Collect a USB ACK before sending at UART speed, avoiding USB RX overflow.
uint8_t txFrame[C71_REPLY_CAPACITY];
size_t txLength=0;
unsigned long lastUsbByte=0;
void setup(){Serial.begin(USB_BAUD);midiUart.begin(MIDI_BAUD);}
void loop(){
  if(txLength&&millis()-lastUsbByte>3000)txLength=0;
  if(midiUart.available())Serial.write((uint8_t)midiUart.read());
  while(Serial.available()){
    uint8_t b=(uint8_t)Serial.read();lastUsbByte=millis();
    if(b>=0xf8)continue;
    if(b==0xf0){txLength=0;txFrame[txLength++]=b;continue;}
    if(!txLength)continue;
    if((b>=0x80&&b!=0xf7)||txLength>=C71_REPLY_CAPACITY){txLength=0;continue;}
    txFrame[txLength++]=b;
    if(b==0xf7){
      for(size_t i=0;i<txLength;i++)midiUart.write(txFrame[i]);
      txLength=0;
    }
  }
}
