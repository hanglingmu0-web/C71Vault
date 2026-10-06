package jp.c71.vault;

import android.system.Os;
import android.system.OsConstants;
import android.util.Base64;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.*;
import org.json.*;

final class Util {
    static final long GIB = 1024L*1024*1024;
    static String b64(byte[] b) { return Base64.encodeToString(b, Base64.NO_WRAP); }
    static byte[] un64(String s) { return Base64.decode(s, Base64.NO_WRAP); }
    static String hex(byte[] b) { StringBuilder s=new StringBuilder(); for(byte x:b)s.append(String.format(java.util.Locale.ROOT,"%02x",x & 255)); return s.toString(); }
    static String hash(byte[] b) throws Exception { return hex(MessageDigest.getInstance("SHA-256").digest(b)); }
    static String hash(File f) throws Exception { MessageDigest md=MessageDigest.getInstance("SHA-256"); try(InputStream in=new FileInputStream(f)){byte[] b=new byte[262144]; int n;while((n=in.read(b))!=-1)md.update(b,0,n);} return hex(md.digest()); }
    static byte[] read(InputStream in, int max) throws IOException { try(in;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1){if(out.size()+n>max)throw new IOException("メタデータが上限を超えています");out.write(b,0,n);}return out.toByteArray();} }
    static JSONObject json(File f) throws Exception { return new JSONObject(new String(read(new FileInputStream(f),1024*1024),StandardCharsets.UTF_8)); }
    static void durable(File f, byte[] bytes) throws Exception { try(FileOutputStream out=new FileOutputStream(f)){out.write(bytes);out.getFD().sync();} }
    static void syncDir(File d) throws Exception { java.io.FileDescriptor fd=Os.open(d.getAbsolutePath(),OsConstants.O_RDONLY,0);try{Os.fsync(fd);}finally{Os.close(fd);} }
    static void atomicJson(File f, JSONObject data) throws Exception { File t=new File(f.getParentFile(),f.getName()+".tmp");durable(t,data.toString().getBytes(StandardCharsets.UTF_8));Files.move(t.toPath(),f.toPath(),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);syncDir(f.getParentFile()); }
    static String id(String s) throws IOException { if(!s.matches("[0-9a-f]{32}"))throw new IOException("IDが不正です");return s; }
    static long size(File f) { if(f.isFile())return f.length();long n=0;File[] a=f.listFiles();if(a!=null)for(File x:a)n+=size(x);return n; }
    static void removeTemp(File f) throws IOException { File[] a=f.listFiles();if(a!=null)for(File x:a)removeTemp(x);if(f.exists()&&!f.delete())throw new IOException("一時ファイルを削除できません"); }
}
