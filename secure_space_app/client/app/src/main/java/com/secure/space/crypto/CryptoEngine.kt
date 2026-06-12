package com.secure.space.crypto

import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyFactory
import java.security.PrivateKey
import java.security.PublicKey
import java.security.SecureRandom
import java.security.spec.PKCS8EncodedKeySpec
import java.security.spec.X509EncodedKeySpec
import java.util.Base64
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec
import java.io.ByteArrayOutputStream
import javax.crypto.Mac

object CryptoEngine {
    private val secureRandom = SecureRandom()

    /**
     * Generate an ECDH key pair.
     * Supports Curve "X25519" (default) or "secp256r1" (by passing "EC" or "ECDH" and customizing parameters).
     */
    fun generateKeyPair(algorithm: String = "X25519"): KeyPair {
        val kpg = KeyPairGenerator.getInstance(algorithm)
        if (algorithm.equals("EC", ignoreCase = true) || algorithm.equals("ECDH", ignoreCase = true)) {
            kpg.initialize(256) // secp256r1
        }
        return kpg.generateKeyPair()
    }

    /**
     * Serialize a public key to PEM format (SubjectPublicKeyInfo DER encoded as Base64).
     */
    fun serializePublicKeyToPem(publicKey: PublicKey): String {
        val encoded = publicKey.encoded
        val base64 = Base64.getMimeEncoder(64, "\n".toByteArray()).encodeToString(encoded)
        return "-----BEGIN PUBLIC KEY-----\n$base64\n-----END PUBLIC KEY-----"
    }

    /**
     * Deserialize a public key from PEM format.
     */
    fun deserializePublicKeyFromPem(pem: String, algorithm: String = "X25519"): PublicKey {
        val cleanPem = pem
            .replace("-----BEGIN PUBLIC KEY-----", "")
            .replace("-----END PUBLIC KEY-----", "")
            .replace("\\s".toRegex(), "")
        val decoded = Base64.getDecoder().decode(cleanPem)
        val keySpec = X509EncodedKeySpec(decoded)
        val kf = KeyFactory.getInstance(algorithm)
        return kf.generatePublic(keySpec)
    }

    /**
     * Serialize a private key to PEM format (PKCS#8 DER encoded as Base64).
     */
    fun serializePrivateKeyToPem(privateKey: PrivateKey): String {
        val encoded = privateKey.encoded
        val base64 = Base64.getMimeEncoder(64, "\n".toByteArray()).encodeToString(encoded)
        return "-----BEGIN PRIVATE KEY-----\n$base64\n-----END PRIVATE KEY-----"
    }

    /**
     * Deserialize a private key from PEM format.
     */
    fun deserializePrivateKeyFromPem(pem: String, algorithm: String = "X25519"): PrivateKey {
        val cleanPem = pem
            .replace("-----BEGIN PRIVATE KEY-----", "")
            .replace("-----END PRIVATE KEY-----", "")
            .replace("\\s".toRegex(), "")
        val decoded = Base64.getDecoder().decode(cleanPem)
        val keySpec = PKCS8EncodedKeySpec(decoded)
        val kf = KeyFactory.getInstance(algorithm)
        return kf.generatePrivate(keySpec)
    }

    /**
     * Derive a shared symmetric key using ECDH key agreement followed by HKDF-SHA256.
     */
    fun deriveSharedKey(
        privateKey: PrivateKey,
        peerPublicKey: PublicKey,
        salt: ByteArray? = null,
        info: ByteArray? = null,
        derivedKeyLength: Int = 32,
        algorithm: String = "X25519"
    ): ByteArray {
        val keyAgreement = KeyAgreement.getInstance(
            if (algorithm.equals("X25519", ignoreCase = true)) "X25519" else "ECDH"
        )
        keyAgreement.init(privateKey)
        keyAgreement.doPhase(peerPublicKey, true)
        val sharedSecret = keyAgreement.generateSecret()
        
        // Use manual HKDF-SHA256 derivation
        return hkdfDerive(sharedSecret, salt, info, derivedKeyLength)
    }

    // --- Manual HKDF-SHA256 implementation ---

    private fun hmacSha256(key: ByteArray, data: ByteArray): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        val secretKey = SecretKeySpec(key, "HmacSHA256")
        mac.init(secretKey)
        return mac.doFinal(data)
    }

    private fun hkdfExtract(salt: ByteArray?, ikm: ByteArray): ByteArray {
        val actualSalt = salt ?: ByteArray(32) // Default to 32 zero bytes
        return hmacSha256(actualSalt, ikm)
    }

    private fun hkdfExpand(prk: ByteArray, info: ByteArray?, length: Int): ByteArray {
        val actualInfo = info ?: ByteArray(0)
        val hashLen = 32
        val n = (length + hashLen - 1) / hashLen
        if (n > 255) throw IllegalArgumentException("Length is too long")
        
        val okm = ByteArrayOutputStream()
        var t = ByteArray(0)
        for (i in 1..n) {
            val bos = ByteArrayOutputStream()
            bos.write(t)
            bos.write(actualInfo)
            bos.write(i)
            t = hmacSha256(prk, bos.toByteArray())
            okm.write(t)
        }
        
        val fullBytes = okm.toByteArray()
        return fullBytes.copyOfRange(0, length)
    }

    private fun hkdfDerive(ikm: ByteArray, salt: ByteArray?, info: ByteArray?, length: Int): ByteArray {
        val prk = hkdfExtract(salt, ikm)
        return hkdfExpand(prk, info, length)
    }

    // --- AES-GCM (256-bit) Encryption/Decryption ---

    /**
     * Encrypt plaintext using AES-GCM with a 256-bit key and a 12-byte random IV.
     * Returns a byte array containing IV + ciphertext.
     */
    fun encryptAesGcm(key: ByteArray, plaintext: ByteArray): ByteArray {
        if (key.size != 32) throw IllegalArgumentException("Key must be 32 bytes (256-bit)")
        val iv = ByteArray(12)
        secureRandom.nextBytes(iv)
        
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val secretKey = SecretKeySpec(key, "AES")
        val gcmSpec = GCMParameterSpec(128, iv)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey, gcmSpec)
        
        val ciphertext = cipher.doFinal(plaintext)
        
        val output = ByteArrayOutputStream()
        output.write(iv)
        output.write(ciphertext)
        return output.toByteArray()
    }

    /**
     * Decrypt raw bytes containing 12-byte IV followed by ciphertext using AES-GCM.
     */
    fun decryptAesGcm(key: ByteArray, ivAndCiphertext: ByteArray): ByteArray {
        if (key.size != 32) throw IllegalArgumentException("Key must be 32 bytes (256-bit)")
        if (ivAndCiphertext.size < 12 + 16) { // 12 bytes IV + at least 16 bytes auth tag
            throw IllegalArgumentException("Ciphertext too short")
        }
        
        val iv = ivAndCiphertext.copyOfRange(0, 12)
        val ciphertext = ivAndCiphertext.copyOfRange(12, ivAndCiphertext.size)
        
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        val secretKey = SecretKeySpec(key, "AES")
        val gcmSpec = GCMParameterSpec(128, iv)
        cipher.init(Cipher.DECRYPT_MODE, secretKey, gcmSpec)
        
        return cipher.doFinal(ciphertext)
    }
}
