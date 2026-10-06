package jp.c71.vault;

import java.io.*;
import java.nio.*;
import java.util.*;
import java.util.zip.CRC32;

/** MIDI 1.0 SysEx framing with 7-bit packing. CRC is not authentication. */
final class SerialFrame {
    static final int MAX_PAYLOAD=512, HEADER=28, MAX_RAW=HEADER+MAX_PAYLOAD+4;
    static final int HELLO=1, START=2, DATA=3, END=4, ABORT=5;
    final int type; final byte[] session,payload; final long sequence;
    SerialFrame(int type,byte[] session,long sequence,byte[] payload){
        this.type=type;this.session=session.clone();this.sequence=sequence;this.payload=payload.clone();
    }
    byte[] raw(){
        if(session.length!=16||payload.length>MAX_PAYLOAD||sequence<0||sequence>0xffffffffL)throw new IllegalArgumentException("frame size");
        ByteBuffer b=ByteBuffer.allocate(HEADER+payload.length+4).order(ByteOrder.BIG_ENDIAN);
        b.put(new byte[]{'C','7','I','S'}).put((byte)1).put((byte)type).put(session).putInt((int)sequence).putShort((short)payload.length).put(payload);
        CRC32 crc=new CRC32();crc.update(b.array(),0,b.position());b.putInt((int)crc.getValue());return b.array();
    }
    byte[] wire(){
        return sysex(raw());
    }
    static byte[] sysex(byte[] raw){
        ByteArrayOutputStream b=new ByteArrayOutputStream();b.write(0xf0);b.write(0x7d);b.write('C');b.write('7');b.write('1');
        for(int p=0;p<raw.length;p+=7){int count=Math.min(7,raw.length-p),high=0;for(int i=0;i<count;i++)high|=((raw[p+i]&255)>>>7)<<i;b.write(high);for(int i=0;i<count;i++)b.write(raw[p+i]&127);}
        b.write(0xf7);return b.toByteArray();
    }
    static SerialFrame parse(byte[] raw)throws IOException {
        if(raw.length<HEADER+4||raw.length>MAX_RAW)throw new IOException("length");
        ByteBuffer b=ByteBuffer.wrap(raw).order(ByteOrder.BIG_ENDIAN);
        if(b.getInt()!=0x43374953||b.get()!=1)throw new IOException("magic/version");
        int type=b.get()&255;byte[] session=new byte[16];b.get(session);long seq=Integer.toUnsignedLong(b.getInt());int len=b.getShort()&65535;
        if(len>MAX_PAYLOAD||raw.length!=HEADER+len+4)throw new IOException("length");
        CRC32 crc=new CRC32();crc.update(raw,0,raw.length-4);
        if(crc.getValue()!=Integer.toUnsignedLong(ByteBuffer.wrap(raw,raw.length-4,4).getInt()))throw new IOException("CRC mismatch");
        if(type<HELLO||type>ABORT)throw new IOException("unknown type");
        boolean nonzero=false;for(byte v:session)nonzero|=v!=0;if(!nonzero)throw new IOException("zero session");
        byte[] payload=new byte[len];b.get(payload);return new SerialFrame(type,session,seq,payload);
    }
    interface Listener {void frame(SerialFrame frame);void error(String error);}
    static final class Parser {
        final Listener listener;final byte[] buffer=new byte[MAX_RAW];int used,prefix,high,group;boolean inside,discard;
        Parser(Listener listener){this.listener=listener;}
        void feed(byte[] bytes,int length){for(int i=0;i<length;i++)accept(bytes[i]&255);}
        void accept(int b){
            // MIDI real-time messages may be interleaved with SysEx.
            if(b>=0xf8)return;
            if(b==0xf0){if(inside&&!discard)listener.error("truncated SysEx");inside=true;used=0;prefix=0;group=0;high=0;discard=false;return;}
            if(b==0xf7){
                if(inside&&!discard){
                    if(prefix!=4||group==1||(group>1&&(high>>>(group-1))!=0))listener.error("invalid 7-bit packing");
                    else try{listener.frame(parse(Arrays.copyOf(buffer,used)));}catch(IOException e){listener.error(e.getMessage());}
                }
                inside=false;used=0;group=0;return;
            }
            if(!inside||discard)return;
            if(b>=0x80){fail("non-realtime MIDI status inside SysEx");inside=false;return;}
            if(prefix<4){int[] id={0x7d,'C','7','1'};if(b!=id[prefix++]){fail("foreign SysEx ID");}return;}
            if(group==0){high=b;group=1;return;}
            if(used==buffer.length){fail("oversize frame");return;}
            buffer[used++]=(byte)(b|(((high>>>(group-1))&1)<<7));group++;if(group==8)group=0;
            if(used==HEADER){int length=((buffer[26]&255)<<8)|(buffer[27]&255);if(length>MAX_PAYLOAD)fail("length");}
        }
        void fail(String why){discard=true;used=0;listener.error(why);}
        void disconnected(){if(inside&&!discard)listener.error("truncated SysEx");used=0;inside=false;group=0;discard=false;}
    }
}
