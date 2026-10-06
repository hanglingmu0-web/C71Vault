package jp.c71.vault;

import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.*;
import java.io.*;
import java.nio.*;
import java.security.*;
import java.util.*;
import static org.junit.Assert.*;

public class IsolatedSerialTest {
    IsolatedReceiver receiver;byte[] session=new byte[16];
    @Before public void prepare(){Arrays.fill(session,(byte)13);receiver=new IsolatedReceiver(r->{});}
    @After public void close(){receiver.close();}
    byte[] data(int n){byte[] b=new byte[n];new Random(42).nextBytes(b);return b;}
    SerialFrame frame(int type,long seq,byte[] b){return new SerialFrame(type,session,seq,b);}
    void send(SerialFrame frame){byte[] wire=frame.wire();for(int i=0;i<wire.length;i+=7){byte[] part=Arrays.copyOfRange(wire,i,Math.min(wire.length,i+7));receiver.feed(part,part.length);}}
    void start(byte[] data)throws Exception{
        send(frame(1,0,new byte[0]));send(frame(2,0,ByteBuffer.allocate(40).putLong(data.length).put(MessageDigest.getInstance("SHA-256").digest(data)).array()));
    }
    void transfer(byte[] data)throws Exception{start(data);int seq=1;for(int p=0;p<data.length;p+=512)send(frame(3,seq++,Arrays.copyOfRange(data,p,Math.min(data.length,p+512))));send(frame(4,seq,new byte[0]));}
    @Test public void random64KiBAndEveryByte()throws Exception{byte[] b=data(65536);transfer(b);assertTrue(receiver.complete);assertEquals(65536,receiver.received);assertEquals(Util.hash(b),receiver.sha256);}
    @Test public void textAnd1KiB()throws Exception{transfer("C71VAULT MIDI TEST".getBytes("US-ASCII"));assertTrue(receiver.complete);session[0]++;transfer(data(1024));assertTrue(receiver.complete);assertEquals(1024,receiver.received);}
    @Test public void crcMismatchInvalidatesTransfer()throws Exception{byte[] b=data(12);start(b);byte[] raw=frame(3,1,b).raw();raw[28]^=1;try{SerialFrame.parse(raw);fail();}catch(IOException expected){assertEquals("CRC mismatch",expected.getMessage());}receiver.error("CRC mismatch");send(frame(4,2,new byte[0]));assertFalse(receiver.complete);}
    @Test public void malformedLengthAndBoundedResynchronization()throws Exception{
        start(data(2));byte[] raw=frame(3,1,new byte[0]).raw();raw[26]=127;byte[] bytes=SerialFrame.sysex(raw);receiver.feed(bytes,bytes.length);assertFalse(receiver.active);assertTrue(receiver.errors>0);
        session[0]++;transfer(data(20));assertTrue(receiver.complete);
    }
    @Test public void oversizedFrameCannotGrowMemory()throws Exception{byte[] b=SerialFrame.sysex(new byte[10000]);receiver.feed(b,b.length);assertTrue(receiver.errors>0);session[0]++;transfer(data(512));assertTrue(receiver.complete);}
    @Test public void missingSequenceCannotSucceed()throws Exception{start(data(10));send(frame(3,2,data(10)));assertFalse(receiver.active);assertFalse(receiver.complete);assertTrue(receiver.lastError.contains("sequence"));}
    @Test public void duplicateSequenceAndEndAreIdempotent()throws Exception{byte[] b=data(10);start(b);SerialFrame d=frame(3,1,b);send(d);send(d);assertEquals(10,receiver.received);SerialFrame e=frame(4,2,new byte[0]);send(e);send(e);assertTrue(receiver.complete);assertEquals(0,receiver.errors);}
    @Test public void conflictingDuplicateAborts()throws Exception{start(data(10));send(frame(3,1,data(10)));send(frame(3,1,new byte[10]));assertFalse(receiver.active);assertTrue(receiver.lastError.contains("duplicate"));}
    @Test public void unknownTypeRejectedByParser()throws Exception{start(data(2));send(frame(99,1,new byte[0]));assertFalse(receiver.active);assertTrue(receiver.lastError.contains("type"));}
    @Test public void disconnectBeforeEndIsNotSuccess()throws Exception{start(data(10));send(frame(3,1,data(10)));receiver.close();assertFalse(receiver.complete);assertFalse(receiver.active);assertTrue(receiver.lastError.contains("disconnected"));}
    @Test public void capacityLimitRejectsBeforeReceive()throws Exception{receiver.limit=32;start(data(64));assertFalse(receiver.active);assertTrue(receiver.lastError.contains("capacity"));assertEquals(0,receiver.received);}
    @Test public void shaMismatchAborts()throws Exception{start(data(10));send(frame(3,1,new byte[10]));send(frame(4,2,new byte[0]));assertFalse(receiver.complete);assertEquals("SHA-256 mismatch",receiver.lastError);}
    @Test public void existingVaultDataUntouched()throws Exception{
        Vault vault=Vault.get(InstrumentationRegistry.getInstrumentation().getTargetContext());File sentinel=new File(vault.archives,"serial-sentinel-"+UUID.randomUUID());byte[] b=data(128);Util.durable(sentinel,b);
        try{transfer(data(1024));assertTrue(receiver.complete);session[0]++;receiver.limit=1;start(data(128));assertArrayEquals(b,java.nio.file.Files.readAllBytes(sentinel.toPath()));}finally{assertTrue(sentinel.delete());}
    }
    @Test public void sessionMismatchAndTruncatedSysExReject()throws Exception{start(data(2));session[0]++;send(frame(3,1,data(2)));assertFalse(receiver.active);byte[] bad={(byte)0xf0,(byte)0x7d,(byte)0xf0};receiver.feed(bad,bad.length);assertEquals("truncated SysEx",receiver.lastError);}
    @Test public void midiDataAreSevenBitAndRealtimeMayInterleave()throws Exception{
        byte[] b=data(512);start(b);byte[] wire=frame(3,1,b).wire();ByteArrayOutputStream mixed=new ByteArrayOutputStream();
        for(int i=0;i<wire.length;i++){if(i>0&&i<wire.length-1)assertTrue((wire[i]&255)<128);mixed.write(wire[i]);mixed.write(0xf8);}
        byte[] bytes=mixed.toByteArray();receiver.feed(bytes,bytes.length);send(frame(4,2,new byte[0]));assertTrue(receiver.complete);
    }
    @Test public void otherMidiStatusAbortsSysEx()throws Exception{start(data(2));byte[] bytes={(byte)0xf0,0x7d,67,55,49,(byte)0x90};receiver.feed(bytes,bytes.length);assertFalse(receiver.active);assertTrue(receiver.lastError.contains("MIDI status"));}
}
