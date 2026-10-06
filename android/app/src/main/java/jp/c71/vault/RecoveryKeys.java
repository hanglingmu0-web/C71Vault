package jp.c71.vault;

import android.app.KeyguardManager;
import android.content.Context;
import android.security.keystore.*;
import java.io.*;
import java.security.*;
import java.security.interfaces.RSAPublicKey;
import java.security.spec.*;
import javax.crypto.Cipher;
import javax.crypto.spec.*;
import org.json.*;

/** RSA private operations require a recent Android device-credential authentication. */
final class RecoveryKeys {
    static final String ALIAS = "C71VaultRecoveryWrappingV2";
    final File directory;
    final KeyStore keystore;
    RecoveryKeys(Context c, File base) throws Exception {
        directory = new File(base, "recovery-keys");
        if (!directory.mkdirs() && !directory.isDirectory()) throw new IOException("鍵の保管領域を作れません");
        keystore = KeyStore.getInstance("AndroidKeyStore"); keystore.load(null);
        if (!keystore.containsAlias(ALIAS)) {
            if (!c.getSystemService(KeyguardManager.class).isDeviceSecure())
                throw new IOException("C71にPIN等の画面ロックを設定してください");
            KeyPairGenerator g = KeyPairGenerator.getInstance("RSA", "AndroidKeyStore");
            g.initialize(new KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_DECRYPT)
                .setKeySize(2048).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_RSA_OAEP)
                .setDigests(KeyProperties.DIGEST_SHA256, KeyProperties.DIGEST_SHA1)
                .setUserAuthenticationRequired(true)
                .setUserAuthenticationParameters(30, KeyProperties.AUTH_DEVICE_CREDENTIAL).build());
            g.generateKeyPair();
        }
    }
    byte[] publicBytes() throws Exception { return keystore.getCertificate(ALIAS).getPublicKey().getEncoded(); }
    static String keyId(String id) throws IOException {
        if (!id.matches("[0-9a-f]{16}")) throw new IOException("復元鍵IDが不正です"); return id;
    }
    boolean has(String id) throws Exception { return new File(directory, keyId(id)+".json").isFile(); }
    static OAEPParameterSpec parameters() {
        return new OAEPParameterSpec("SHA-256", "MGF1", MGF1ParameterSpec.SHA1, PSource.PSpecified.DEFAULT);
    }
    byte[] unwrap(String capsule, String id) throws Exception {
        byte[] encrypted = Util.un64(capsule);
        if (encrypted.length != 256) throw new IOException("鍵カプセルのサイズが不正です");
        Cipher cipher = Cipher.getInstance("RSA/ECB/OAEPPadding");
        cipher.init(Cipher.DECRYPT_MODE, keystore.getKey(ALIAS,null), parameters());
        byte[] key = cipher.doFinal(encrypted);
        if (key.length != 32 || !Util.hash(key).substring(0,16).equals(keyId(id))) {
            java.util.Arrays.fill(key,(byte)0); throw new IOException("復元鍵IDが一致しません");
        }
        return key;
    }
    synchronized void approveImport(String id, String capsule) throws Exception {
        if (has(id)) return; // Existing custody is never replaced by a PC request.
        byte[] key = unwrap(capsule,id);
        java.util.Arrays.fill(key,(byte)0);
        Util.atomicJson(new File(directory,keyId(id)+".json"),
            new JSONObject().put("key_id",id).put("capsule",capsule));
    }
    String recoverFor(String id, String recipient) throws Exception {
        PublicKey publicKey = KeyFactory.getInstance("RSA").generatePublic(new X509EncodedKeySpec(Util.un64(recipient)));
        if (!(publicKey instanceof RSAPublicKey rsa) || rsa.getModulus().bitLength()!=2048)
            throw new IOException("回収先の鍵が不正です");
        byte[] key = unwrap(Util.json(new File(directory,keyId(id)+".json")).getString("capsule"),id);
        try {
            Cipher c = Cipher.getInstance("RSA/ECB/OAEPPadding"); c.init(Cipher.ENCRYPT_MODE,publicKey,parameters());
            return Util.b64(c.doFinal(key));
        } finally { java.util.Arrays.fill(key,(byte)0); }
    }
}
