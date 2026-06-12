package com.secure.space.crypto

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNotNull
import org.junit.Test

class CryptoEngineTest {

    @Test
    fun testKeyPairGeneration() {
        val keyPair = CryptoEngine.generateKeyPair("X25519")
        assertNotNull(keyPair.private)
        assertNotNull(keyPair.public)
        assertEquals("X25519", keyPair.public.algorithm)
    }

    @Test
    fun testPublicKeySerializationDeserialization() {
        val keyPair = CryptoEngine.generateKeyPair("X25519")
        val pem = CryptoEngine.serializePublicKeyToPem(keyPair.public)
        
        assert(pem.contains("-----BEGIN PUBLIC KEY-----"))
        assert(pem.contains("-----END PUBLIC KEY-----"))

        val deserialized = CryptoEngine.deserializePublicKeyFromPem(pem, "X25519")
        assertArrayEquals(keyPair.public.encoded, deserialized.encoded)
    }

    @Test
    fun testPrivateKeySerializationDeserialization() {
        val keyPair = CryptoEngine.generateKeyPair("X25519")
        val pem = CryptoEngine.serializePrivateKeyToPem(keyPair.private)
        
        assert(pem.contains("-----BEGIN PRIVATE KEY-----"))
        assert(pem.contains("-----END PRIVATE KEY-----"))

        val deserialized = CryptoEngine.deserializePrivateKeyFromPem(pem, "X25519")
        assertArrayEquals(keyPair.private.encoded, deserialized.encoded)
    }

    @Test
    fun testSharedKeyAgreement() {
        val aliceKeyPair = CryptoEngine.generateKeyPair("X25519")
        val bobKeyPair = CryptoEngine.generateKeyPair("X25519")

        val salt = "test-salt".toByteArray()
        val info = "test-info".toByteArray()

        val aliceShared = CryptoEngine.deriveSharedKey(
            aliceKeyPair.private,
            bobKeyPair.public,
            salt = salt,
            info = info
        )

        val bobShared = CryptoEngine.deriveSharedKey(
            bobKeyPair.private,
            aliceKeyPair.public,
            salt = salt,
            info = info
        )

        assertEquals(32, aliceShared.size)
        assertEquals(32, bobShared.size)
        assertArrayEquals(aliceShared, bobShared)

        val charlieKeyPair = CryptoEngine.generateKeyPair("X25519")
        val charlieShared = CryptoEngine.deriveSharedKey(
            charlieKeyPair.private,
            bobKeyPair.public,
            salt = salt,
            info = info
        )
        
        var match = true
        for (i in 0 until 32) {
            if (aliceShared[i] != charlieShared[i]) {
                match = false
                break
            }
        }
        assertEquals(false, match)
    }

    @Test
    fun testAesGcmEncryptionDecryption() {
        val key = ByteArray(32) { i -> i.toByte() }
        val plaintext = "Hello Secure Space End-to-End!".toByteArray()

        val encrypted = CryptoEngine.encryptAesGcm(key, plaintext)
        assert(encrypted.size > 12 + plaintext.size)

        val decrypted = CryptoEngine.decryptAesGcm(key, encrypted)
        assertArrayEquals(plaintext, decrypted)
    }
}
