// MIDI 1.0 SysEx test source for UNO R3 and UNO R4 WiFi/Minima.
// USB bridge stays at 115200 baud. Future inter-board MIDI UART uses 31250.
// 0x7D is a development/non-commercial SysEx ID, not an assigned product ID.
#include <Arduino.h>
const unsigned long USB_BAUD = 115200;
const unsigned long MIDI_UART_BAUD = 31250;
const uint16_t CHUNK = 128;
const uint8_t HASHES[3][32] = {{178,97,46,161,175,40,86,196,110,197,142,142,224,19,237,200,211,139,255,225,84,179,53,41,37,67,205,205,249,2,87,164},
{183,154,94,250,55,67,193,241,220,64,23,181,75,11,228,131,154,210,47,192,211,212,157,209,151,223,72,220,79,37,41,29},
{170,234,237,175,212,132,90,10,93,234,7,144,246,126,59,193,180,110,128,96,144,208,87,219,188,28,23,184,101,209,84,191}};
uint32_t crc,randomState;uint8_t packed[7],packCount,session[16];
void packFlush(){if(!packCount)return;uint8_t high=0;for(uint8_t i=0;i<packCount;i++)high|=(packed[i]>>7)<<i;Serial.write(high);for(uint8_t i=0;i<packCount;i++)Serial.write(packed[i]&127);packCount=0;}
void encoded(uint8_t v){packed[packCount++]=v;if(packCount==7)packFlush();}
void raw(uint8_t v){crc^=v;for(uint8_t b=0;b<8;b++)crc=(crc>>1)^((crc&1)?0xedb88320UL:0);encoded(v);}
void word32(uint32_t v){raw(v>>24);raw(v>>16);raw(v>>8);raw(v);}
void beginFrame(uint8_t type,uint32_t seq,uint16_t length){
 Serial.write(0xf0);Serial.write(0x7d);Serial.write('C');Serial.write('7');Serial.write('1');packCount=0;crc=0xffffffffUL;
 raw('C');raw('7');raw('I');raw('S');raw(1);raw(type);for(uint8_t i=0;i<16;i++)raw(session[i]);word32(seq);raw(length>>8);raw(length);
}
void endFrame(){uint32_t c=crc^0xffffffffUL;encoded(c>>24);encoded(c>>16);encoded(c>>8);encoded(c);packFlush();Serial.write(0xf7);Serial.flush();delay(12);}
uint8_t randomByte(){randomState^=randomState<<13;randomState^=randomState>>17;randomState^=randomState<<5;return randomState&255;}
void runCase(uint8_t which){
 const char text[]="C71VAULT MIDI TEST";uint32_t size=which==0?sizeof(text)-1:(which==1?1024UL:65536UL);
 for(uint8_t i=0;i<16;i++)session[i]=0x40+which;session[0]=which+1;
 beginFrame(1,0,0);endFrame();beginFrame(2,0,40);word32(0);word32(size);for(uint8_t i=0;i<32;i++)raw(HASHES[which][i]);endFrame();
 randomState=which==1?0x12345678UL:0x9abcdef1UL;uint32_t offset=0,seq=1;
 while(offset<size){uint16_t count=(size-offset)>CHUNK?CHUNK:(size-offset);beginFrame(3,seq++,count);for(uint16_t i=0;i<count;i++)raw(which==0?text[offset+i]:randomByte());endFrame();offset+=count;}
 beginFrame(4,seq,0);endFrame();delay(2000);
}
void setup(){Serial.begin(USB_BAUD);}
void loop(){
 if(!Serial){delay(100);return;}
 delay(5000);for(uint8_t i=0;i<3;i++)runCase(i);
 // Repeat allows opening the Android receiver after reconnecting the board.
 delay(15000);
}
