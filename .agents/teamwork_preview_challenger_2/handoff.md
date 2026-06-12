# Compatibility Handoff Report - Python ClientSim & Kotlin MessageManager

## 1. Observation

We compared the cryptographic conventions in the Python simulation client (`secure_space_app/tests/client_sim.py`) and the Kotlin Android client (`secure_space_app/client/app/src/main/java/com/secure/space/MessageManager.kt` and `secure_space_app/client/app/src/main/java/com/secure/space/crypto/CryptoEngine.kt`).

Below are the verbatim implementations extracted from the source files:

### Key Generation & Serialization (X25519):
- **Python** (`client_sim.py`, line 18-25):
  ```python
  self.private_key = x25519.X25519PrivateKey.generate()
  self.public_key = self.private_key.public_key()
  self.public_key_pem = self.public_key.public_bytes(
      encoding=serialization.Encoding.PEM,
      format=serialization.PublicFormat.SubjectPublicKeyInfo
  ).decode('utf-8')
  ```
- **Kotlin** (`CryptoEngine.kt`, line 37-41):
  ```kotlin
  fun serializePublicKeyToPem(publicKey: PublicKey): String {
      val encoded = publicKey.encoded
      val base64 = Base64.getMimeEncoder(64, "\n".toByteArray()).encodeToString(encoded)
      return "-----BEGIN PUBLIC KEY-----\n$base64\n-----END PUBLIC KEY-----"
  }
  ```

### ECDH Shared Key Agreement & HKDF:
- **Python** (`client_sim.py`, line 55-67):
  ```python
  def _derive_shared_key(self, peer_public_key_pem: str) -> bytes:
      peer_pubkey = serialization.load_pem_public_key(peer_public_key_pem.encode('utf-8'))
      shared_key_raw = self.private_key.exchange(peer_pubkey)
      derived_key = HKDF(
          algorithm=hashes.SHA256(),
          length=32,
          salt=None,
          info=b'secure-space-e2ee-key-agreement'
      ).derive(shared_key_raw)
      return derived_key
  ```
- **Kotlin** (`MessageManager.kt`, line 53-60):
  ```kotlin
  private fun deriveSharedKey(peerPublicKey: PublicKey): ByteArray {
      return CryptoEngine.deriveSharedKey(
          privateKey = keyPair.private,
          peerPublicKey = peerPublicKey,
          salt = null,
          info = "secure-space-e2ee-key-agreement".toByteArray()
      )
  }
  ```
- **Kotlin HKDF implementation** (`CryptoEngine.kt`, line 111-140):
  ```kotlin
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
          bos.write(i) // Writes the single-byte representation of i (1, 2...)
          t = hmacSha256(prk, bos.toByteArray())
          okm.write(t)
      }
      
      val fullBytes = okm.toByteArray()
      return fullBytes.copyOfRange(0, length)
  }
  ```

### AES-GCM Encryption / Decryption:
- **Python** (`client_sim.py`, line 70-86):
  ```python
  @staticmethod
  def encrypt_aes_gcm(key: bytes, plaintext: bytes) -> str:
      aesgcm = AESGCM(key)
      iv = os.urandom(12)
      ciphertext = aesgcm.encrypt(iv, plaintext, None)
      return (iv + ciphertext).hex()
  ```
- **Kotlin** (`CryptoEngine.kt`, line 148-164):
  ```kotlin
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
  ```

### File Metadata Schema Mismatch:
- **Python File Metadata Creation** (`client_sim.py`, line 345-350):
  ```python
  metadata = {
      "file_id": file_id,
      "file_name": file_name,
      "encrypted_file_key": encrypted_file_key_hex
  }
  ```
- **Kotlin File Metadata Model** (`Models.kt`, line 98-103):
  ```kotlin
  data class FileMetadata(
      @SerializedName("file_id") val fileId: String,
      @SerializedName("file_name") val fileName: String,
      @SerializedName("encrypted_file_key") val encryptedFileKey: String,
      @SerializedName("iv") val iv: String
  )
  ```

---

## 2. Logic Chain

1. **Algorithm & Parameter Parity**: 
   - Both languages use standard ECDH Curve X25519.
   - Both use AES-256-GCM with a 12-byte (96-bit) IV and a 16-byte (128-bit) authentication tag.
   
2. **Key Derivation (HKDF-SHA256)**:
   - When Python's KDF defines `salt=None`, the library defaults to 32 zero bytes (the digest length of SHA-256). 
   - Kotlin's manual implementation handles `salt = null` by defaulting to `ByteArray(32)` (32 zero bytes), producing mathematical alignment.
   - The info tag `b'secure-space-e2ee-key-agreement'` in Python matches `"secure-space-e2ee-key-agreement".toByteArray()` in Kotlin.
   - Kotlin's manual loop counter byte write `bos.write(i)` correctly writes a single octet representing the counter (0x01, 0x02...), in line with RFC 5869 Section 2.3.

3. **PEM Representation & Parsing**:
   - Kotlin uses standard `Base64.getMimeEncoder(64, "\n".toByteArray())` which replicates Python's standard PEM serialization format.
   - Kotlin's deserializer replaces all whitespaces/newlines before decoding Base64, which is robust against platform line ending differences (`\r\n` vs `\n`).

4. **Symmetric Encryption IV Serialization**:
   - Python's `AESGCM` automatically appends the 16-byte tag to the ciphertext. Thus, `iv + ciphertext` in Python equals `12-byte IV + ciphertext + 16-byte tag`.
   - In Java's `Cipher`, `cipher.doFinal` returns `ciphertext + 16-byte tag` for GCM. Prepending the `iv` array creates the identical `12-byte IV + ciphertext + 16-byte tag` layout.
   - Text messaging hex encodes the entire package (lowercase hex). File messaging keeps the raw binary package.

5. **JSON Schema Compatibility**:
   - Kotlin matches Python's JSON keys via `@SerializedName` annotation.
   - However, Kotlin includes a non-nullable `iv` field in `FileMetadata` class. Since Python omits `iv` when sharing files, Gson will deserialize the field to `null` in Kotlin. If a developer attempts to access `iv` in Kotlin, a NullPointerException will occur.

---

## 3. Caveats

- **No Live Compilation/Execution**: Live test execution could not be verified on the system due to the absence of Gradle/Java JDK on the console path and command permission timeouts. Analysis is performed through rigorous line-by-line verification of JVM/JCA behavior and RFC compliance.
- **Nullability Mismatch Mitigation**: While the Kotlin client does not currently read the `iv` field from `FileMetadata` inside `downloadAndDecryptFile` or elsewhere, future revisions might access it, leading to a crash.

---

## 4. Conclusion & Compatibility Matrix

Python's `ClientSim` and Kotlin's `MessageManager`/`CryptoEngine` are **fully cryptographically compatible**. A payload encrypted by Python ClientSim can be decrypted by Kotlin MessageManager, and vice versa.

### Cryptographic Parity Matrix

| Cryptographic Parameter | Python ClientSim | Kotlin MessageManager | Compatibility Status | Notes |
| :--- | :--- | :--- | :--- | :--- |
| **Key Agreement Curve** | X25519 (via `cryptography`) | X25519 (via JCE KeyFactory) | **Compatible** | Math aligns fully |
| **Public Key PEM Structure** | SubjectPublicKeyInfo (SPKI) | SubjectPublicKeyInfo (SPKI) | **Compatible** | Standard 64-char line width |
| **HKDF Algorithm** | HKDF-SHA256 | HKDF-SHA256 (Manual JCE HMAC) | **Compatible** | RFC 5869 compliant |
| **HKDF Salt** | None (Defaults to 32 zero bytes) | null (Defaults to 32 zero bytes) | **Compatible** | Identical salt inputs |
| **HKDF Info Tag** | `b'secure-space-e2ee-key-agreement'` | `"secure-space-e2ee-key-agreement".toByteArray()` | **Compatible** | UTF-8 / ASCII bytes match |
| **Symmetric Encryption** | AES-256-GCM | AES-256-GCM | **Compatible** | Identical key length |
| **IV / Tag Lengths** | IV: 12 bytes / Tag: 16 bytes | IV: 12 bytes / Tag: 16 bytes | **Compatible** | 96-bit IV, 128-bit tag |
| **IV Serialization (Text)** | Hex of `[IV] + [Ciphertext] + [Tag]` | Hex of `[IV] + [Ciphertext] + [Tag]` | **Compatible** | Lowercase hex strings |
| **IV Serialization (Files)**| Raw `[IV] + [Ciphertext] + [Tag]` bytes| Raw `[IV] + [Ciphertext] + [Tag]` bytes| **Compatible** | Multi-part form stream |
| **File Metadata Schema** | `{"file_id", "file_name", "encrypted_file_key"}` | `{"file_id", "file_name", "encrypted_file_key", "iv"}` | **Latent Risk** | Kotlin's `iv` field parses as `null` when receiving from Python. |

---

## 5. Verification Method

To independently verify the compatibility:
1. Ensure a machine has both Python 3.9+ (with `cryptography`) and Java JDK (with Gradle) installed.
2. In Kotlin `MessageManagerTest.kt`, run `testUnitFileSharing` and `testUnitDirectMessaging` to verify the Kotlin-to-Kotlin correctness.
3. To test cross-compatibility, compile `CryptoEngine.kt` to a JAR, and run a test script that generates a key pair, encrypts a plaintext in Kotlin, prints the hex string, and passes it to Python `ClientSim.decrypt_aes_gcm` to decrypt it successfully.
4. **Invalidation conditions**: Modifying the HKDF Info string, changing the IV location from prepended to appended, changing the AES-GCM tag length from 128 to 96, or altering the public key serialization format to PKCS1.
