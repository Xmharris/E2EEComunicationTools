# E2EE & Cryptographic Gap Report

This report documents the security flaws, design weaknesses, and untested code paths identified in the client-side cryptographic engine (`CryptoEngine.kt`), the message manager (`MessageManager.kt`), and the existing E2E test suite (`test_e2e_suite.py`).

---

## 1. Cryptographic Vulnerabilities & Design Flaws

### Finding 1: Static Shared Symmetric Keys (No Forward Secrecy)
* **Location**: `MessageManager.kt` (lines 53-60)
* **Mechanism**: 
  The function `deriveSharedKey` derives a symmetric key for 1-on-1 direct messages (DMs) using ECDH:
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
  Since the user's ECDH key pair is generated once upon client initialization and never rotates, and the `salt` is hardcoded to `null` with a fixed `info` string, the derived key between any two users is **fully static**.
* **Impact**: CRITICAL. If an attacker compromises a user's private key, they can decrypt all past and future direct messages (DMs) exchanged with any peer. There is no Perfect Forward Secrecy (PFS).

### Finding 2: Missing Group Key Rotation (Post-Compromise & Forward Secrecy Violations)
* **Location**: `MessageManager.kt` (lines 287-291)
* **Mechanism**: 
  When a member leaves a space via `leaveSpace`, their local client removes the key from the `spaceKeys` map:
  ```kotlin
  fun leaveSpace(spaceId: String): LeaveSpaceResponse {
      val response = apiClient.leaveSpace(LeaveSpaceRequest(spaceId, userId))
      spaceKeys.remove(spaceId)
      return response
  }
  ```
  However, the remaining space members/creator do **not** generate and distribute a new space key. The space key remains unchanged.
* **Impact**: HIGH. A departed member who retains a copy of the space key (either in memory, storage, or by having logged it prior to leaving) can continue to decrypt all future messages sent in that space. Conversely, a newly added member can decrypt historic messages if they intercept the encrypted traffic.

### Finding 3: Lack of Digital Signatures / Lack of Non-Repudiation
* **Location**: `MessageManager.kt` (lines 122-135)
* **Mechanism**: 
  All space messages are encrypted with the shared `spaceKey` using AES-GCM. AES-GCM provides message integrity and confidentiality, but because the symmetric key is shared among all members, any member of the space can construct, encrypt, and upload a message claiming it was sent by another member.
* **Impact**: HIGH. There is no non-repudiation. A malicious space member can forge messages, files, or meeting schedules that appear to come from other members. Individual messages are not digitally signed using a private signing key (e.g., Ed25519).

### Finding 4: Replay Attack Vulnerability
* **Location**: `MessageManager.kt` (lines 90-104)
* **Mechanism**: 
  When sending a direct message, the plaintext byte array is passed directly to `encryptAesGcm`:
  ```kotlin
  val encryptedPayload = CryptoEngine.encryptAesGcm(sharedKey, text.toByteArray(Charsets.UTF_8)).toHex()
  ```
  The plaintext does not include any sequence number, timestamp, sender/recipient identifier, or unique session token.
* **Impact**: HIGH. An attacker (or a compromised backend) can capture a valid encrypted DM or space message payload and replay it later. The recipient's client will decrypt it successfully and display it as a new, authentic message.

### Finding 5: Unauthenticated Public Key Directory (MITM Risk)
* **Location**: `MessageManager.kt` (lines 46-51)
* **Mechanism**: 
  Peer public keys are fetched directly from the backend API:
  ```kotlin
  private fun getPeerPublicKey(peerId: String): PublicKey {
      val users = apiClient.getUsers()
      val user = users.find { it.userId == peerId }
          ?: throw IOException("User $peerId not found")
      return CryptoEngine.deserializePublicKeyFromPem(user.publicKey, "X25519")
  }
  ```
  There is no out-of-band verification (e.g., QR code scans, numeric fingerprints) or Trust-On-First-Use (TOFU) pin checking.
* **Impact**: HIGH. A compromised or malicious server can supply a fake public key (belonging to the server or an attacker) when Alice asks for Bob's public key. The server can then intercept, decrypt, and re-encrypt direct messages or space keys exchanged between Alice and Bob (Man-in-the-Middle).

### Finding 6: Uncaught Decryption Exceptions (Crash Hazard)
* **Location**: `CryptoEngine.kt` (lines 169-184) and `MessageManager.kt` (e.g., `receiveDirectMessages`)
* **Mechanism**: 
  If AES-GCM decryption fails due to ciphertext corruption, a tampered authentication tag, or an incorrect key, Java's `cipher.doFinal()` throws an `AEADBadTagException` (or similar). These exceptions are not caught or handled within `MessageManager.kt`.
* **Impact**: MEDIUM. A malicious server or network attacker can inject corrupted payloads, causing the client application to crash when retrieving and processing messages/files/meetings.

---

## 2. Untested Code Paths & Edge Cases

The following areas are currently not covered by the E2E test suite:

1. **Tampered/Corrupted Ciphertexts**: There are no tests verifying that modified ciphertext bytes or altered authentication tags are caught cleanly without causing unhandled exceptions/crashes.
2. **Invalid/Malformed PEM Deserialization**: The error paths in `deserializePublicKeyFromPem` and `deserializePrivateKeyFromPem` (e.g. truncated keys, wrong algorithm headers, empty strings) are never exercised.
3. **Invalid/Short IVs**: The logic in `decryptAesGcm` that checks for `ivAndCiphertext.size < 12 + 16` is not tested.
4. **Unsupported/Mismatched Key Curves**: The interop of curves (e.g. attempting ECDH between an X25519 key and an EC secp256r1 key) and the resulting exception paths are untested.
5. **Post-Leave Space Key Eavesdropping**: No tests verify whether a departed member is statically blocked from decrypting future space messages if they possess the old space key.

---

## 3. Recommended Remediation Plan

1. **Ratchet-based Key Agreement (Perfect Forward Secrecy)**: Implement the Double Ratchet Algorithm (or a simplified version using HKDF updates per message) to ensure keys evolve with every message.
2. **Epoch-based Group Key Rotation**: Whenever a member joins or leaves a space, the space key must be rotated. The space creator (or admin) should generate a new key and distribute it to all current members encrypted under their individual ECDH shared keys.
3. **Individual Digital Signatures**: Generate an Ed25519 signature key pair during registration. Every outgoing message payload must be signed by the sender's private key, and the signature must be verified by the recipient using the sender's public signing key.
4. **Payload Metadata Binding**: Include metadata in the plaintext payload prior to encryption:
   - Sender ID
   - Recipient ID / Space ID
   - Timestamp (ISO 8601)
   - Monotonically increasing sequence number
   Verify this metadata upon decryption to prevent replays, reflection attacks, and destination confusion.
5. **Out-of-Band Key Verification**: Expose key fingerprints (hashes of the public keys) to the UI so users can verify them out-of-band to prevent MITM attacks.
