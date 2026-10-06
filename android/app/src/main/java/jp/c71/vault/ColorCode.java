package jp.c71.vault;

import com.google.zxing.*;
import com.google.zxing.common.HybridBinarizer;
import com.google.zxing.common.*;
import com.google.zxing.qrcode.detector.Detector;
import com.google.zxing.qrcode.QRCodeReader;
import java.io.*;
import java.security.MessageDigest;
import java.util.*;

/** Project-specific two-plane four-color code. Each plane is a byte-mode QR. */
final class ColorCode {
    static final int LAYER_HEADER=23;
    static byte[] decodeNv21(byte[] nv21,int width,int height)throws Exception {
        if(width<=0||height<=0||(width&1)!=0||(height&1)!=0
                ||nv21.length<(long)width*height*3/2)throw new IOException("NV21 frame size");
        int size=width*height;
        byte[] red=new byte[size],blue=new byte[size];
        for(int y=0;y<height;y++)for(int x=0;x<width;x++){
            int index=y*width+x,uv=size+(y/2)*width+(x&~1);
            int luminance=Math.max(0,(nv21[index]&255)-16)*1192;
            int v=(nv21[uv]&255)-128,u=(nv21[uv+1]&255)-128;
            red[index]=(byte)Math.max(0,Math.min(255,(luminance+1634*v)>>10));
            blue[index]=(byte)Math.max(0,Math.min(255,(luminance+2066*u)>>10));
        }
        return decodePlanes(red,blue,width,height);
    }
    static byte[] decodePixels(int[] rgb,int width,int height)throws Exception {
        if(rgb.length!=width*height)throw new IOException("RGB frame size");
        byte[] red=new byte[rgb.length],blue=new byte[rgb.length];
        for(int i=0;i<rgb.length;i++){red[i]=(byte)(rgb[i]>>16);blue[i]=(byte)rgb[i];}
        return decodePlanes(red,blue,width,height);
    }
    static byte[] decodePlanes(byte[] red,byte[] blue,int width,int height)throws Exception {
        byte[] first=null,second=null;
        try{first=decodePlane(red,width,height);}catch(ReaderException ignored){}
        try{second=decodePlane(blue,width,height);}catch(ReaderException ignored){}
        if(first==null&&second!=null)first=decodeUsingGeometry(red,blue,width,height);
        if(second==null&&first!=null)second=decodeUsingGeometry(blue,red,width,height);
        if(first==null||second==null)throw NotFoundException.getNotFoundInstance();
        return join(first,second);
    }
    static byte[] decodeUsingGeometry(byte[] target,byte[] reference,int width,int height)throws Exception {
        BitMatrix ref=new BinaryBitmap(new HybridBinarizer(new PlanarYUVLuminanceSource(reference,width,height,0,0,width,height,false))).getBlackMatrix();
        DetectorResult detected=new Detector(ref).detect(Collections.singletonMap(DecodeHintType.TRY_HARDER,Boolean.TRUE));
        int n=detected.getBits().getWidth();ResultPoint[] p=detected.getPoints();
        ResultPoint bottomLeft=p[0],topLeft=p[1],topRight=p[2];
        float brx=topRight.getX()+bottomLeft.getX()-topLeft.getX(),bry=topRight.getY()+bottomLeft.getY()-topLeft.getY(),ideal=n-3.5f;
        if(p.length>3){brx=p[3].getX();bry=p[3].getY();ideal=n-6.5f;}
        PerspectiveTransform transform=PerspectiveTransform.quadrilateralToQuadrilateral(
                3.5f,3.5f,n-3.5f,3.5f,ideal,ideal,3.5f,n-3.5f,
                topLeft.getX(),topLeft.getY(),topRight.getX(),topRight.getY(),brx,bry,bottomLeft.getX(),bottomLeft.getY());
        BitMatrix source=new BinaryBitmap(new HybridBinarizer(new PlanarYUVLuminanceSource(target,width,height,0,0,width,height,false))).getBlackMatrix();
        BitMatrix grid=GridSampler.getInstance().sampleGrid(source,n,n,transform);
        DecoderResult decoded=new com.google.zxing.qrcode.decoder.Decoder().decode(grid);
        List<byte[]> bytes=decoded.getByteSegments();
        if(bytes==null||bytes.size()!=1)throw new IOException("QR byte segment required");
        return bytes.get(0);
    }
    static byte[] decodePlane(byte[] plane,int width,int height)throws Exception {
        LuminanceSource source=new PlanarYUVLuminanceSource(plane,width,height,0,0,width,height,false);
        Result result=new QRCodeReader().decode(new BinaryBitmap(new HybridBinarizer(source)),
                Collections.singletonMap(DecodeHintType.TRY_HARDER,Boolean.TRUE));
        Map<ResultMetadataType,Object> metadata=result.getResultMetadata();
        if(metadata==null||!(metadata.get(ResultMetadataType.BYTE_SEGMENTS) instanceof List<?>))throw new IOException("QR byte segment required");
        List<?> segments=(List<?>)metadata.get(ResultMetadataType.BYTE_SEGMENTS);
        if(segments.size()!=1||!(segments.get(0) instanceof byte[]))throw new IOException("Exactly one byte segment required");
        return (byte[])segments.get(0);
    }
    static byte[] join(byte[] a,byte[] b)throws Exception {
        byte[][] parts=new byte[2][];byte[] hash=null;int size=0;
        for(byte[] raw:new byte[][]{a,b}){
            if(raw.length<LAYER_HEADER)throw new IOException("Short layer");
            DataInputStream in=new DataInputStream(new ByteArrayInputStream(raw));
            if(!Arrays.equals(ColorOpticalReceiver.read(in,4),new byte[]{'C','7','L','2'}))throw new IOException("Layer magic");
            int index=in.readUnsignedByte(),length=in.readUnsignedShort();byte[] tag=ColorOpticalReceiver.read(in,16);
            if(index>1||parts[index]!=null||length<ColorOpticalReceiver.HEADER+1||length>ColorOpticalReceiver.MAX_PACKET)throw new IOException("Layer header");
            if(hash!=null&&(length!=size||!Arrays.equals(hash,tag)))throw new IOException("Mixed frames");
            hash=tag;size=length;int expected=index==0?(size+1)/2:size/2;
            if(in.available()!=expected)throw new IOException("Layer length");
            parts[index]=ColorOpticalReceiver.read(in,expected);
        }
        byte[] packet=new byte[size];System.arraycopy(parts[0],0,packet,0,parts[0].length);
        System.arraycopy(parts[1],0,packet,parts[0].length,parts[1].length);
        if(!Arrays.equals(hash,Arrays.copyOf(MessageDigest.getInstance("SHA-256").digest(packet),16)))throw new IOException("Mixed or damaged color planes");
        return packet;
    }
}
