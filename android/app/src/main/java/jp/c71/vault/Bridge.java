package jp.c71.vault;

import android.content.*;
import android.database.Cursor;
import android.net.Uri;
import android.provider.DocumentsContract;
import java.io.*;
import java.util.*;

final class Bridge {
    final ContentResolver cr; final Uri tree,root;
    Bridge(Context c, String u) { cr=c.getContentResolver();tree=Uri.parse(u);root=DocumentsContract.buildDocumentUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree)); }
    Map<String,Uri> entries() throws Exception {
        Map<String,Uri> m=new TreeMap<>();Uri children=DocumentsContract.buildChildDocumentsUriUsingTree(tree,DocumentsContract.getTreeDocumentId(tree));
        try(Cursor cur=cr.query(children,new String[]{"document_id","_display_name"},null,null,null)) {
            if(cur==null)throw new IOException("転送フォルダを読めません");
            while(cur.moveToNext()){if(m.size()>=4096)throw new IOException("転送フォルダのファイルが多すぎます");m.put(cur.getString(1),DocumentsContract.buildDocumentUriUsingTree(tree,cur.getString(0)));}
        }return m;
    }
    byte[] read(Uri u,int max)throws Exception { InputStream in=cr.openInputStream(u);if(in==null)throw new IOException("入力を開けません");return Util.read(in,max); }
    InputStream input(Uri u)throws Exception { InputStream in=cr.openInputStream(u);if(in==null)throw new IOException("入力を開けません");return in; }
    Uri outputUri(String name)throws Exception { Uri u=entries().get(name);if(u==null)u=DocumentsContract.createDocument(cr,root,"application/octet-stream",name);if(u==null)throw new IOException("出力を作れません");return u; }
    void write(String name,byte[] b)throws Exception { try(OutputStream out=cr.openOutputStream(outputUri(name),"wt")){if(out==null)throw new IOException("出力を開けません");out.write(b);} }
    void copyOut(String name,File src)throws Exception { try(InputStream in=new FileInputStream(src);OutputStream out=cr.openOutputStream(outputUri(name),"wt")){if(out==null)throw new IOException("出力を開けません");byte[] b=new byte[262144];int n;while((n=in.read(b))!=-1)out.write(b,0,n);} }
    void delete(Uri u)throws Exception { DocumentsContract.deleteDocument(cr,u); }
}
