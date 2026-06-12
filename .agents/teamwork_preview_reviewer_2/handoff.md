# Handoff Report — Security and Cryptographic Review of Kotlin Client

## 1. Observation

- **Implementation Location**: The Kotlin client implementation files are located under `secure_space_app/client/`. Specifically:
  - `secure_space_app/client/app/src/main/java/com/secure/space/crypto/CryptoEngine.kt` (lines 1 to 186)
  - `secure_space_app/client/app/src/main/java/com/secure/space/MessageManager.kt` (lines 1 to 294)
  - `secure_space_app/client/app/src/test/java/com/secure/space/MessageManagerTest.kt` (lines 1 to 425)

- **Peer Derivation Bug**: In `MessageManager.kt`, lines 271 to 280, the `downloadAndDecryptFile` function is defined as:
  ```kotlin
  fun downloadAndDecryptFile(fileId: String, encryptedFileKeyHex: String, spaceId: String?, recipientId: String?): ByteArray {
      val channelKey = if (spaceId != null) {
          spaceKeys[spaceId]
              ?: throw IllegalStateException("No key for space $spaceId found locally")
      } else {
          val peerId = if (recipientId == userId) recipientId else recipientId ?: throw IllegalArgumentException("Missing recipientId")
          val peerPublicKey = getPeerPublicKey(peerId)
          val sharedKey = deriveSharedKey(peerPublicKey)
          sharedKey
      }
  ```

- **Redundant Condition**: In `MessageManager.kt`, line 276:
  ```kotlin
  val peerId = if (recipientId == userId) recipientId else recipientId ?: throw IllegalArgumentException("Missing recipientId")
  ```

- **Test Setup in Unit Tests**: In `MessageManagerTest.kt`, lines 206 to 212:
  ```kotlin
  val downloadedBytes = bob.downloadAndDecryptFile(
      fileId = metadata.fileId,
      encryptedFileKeyHex = metadata.encryptedFileKey,
      spaceId = null,
      recipientId = "bob"
  )
  ```

- **In-Memory Space Key Discarding**: In `MessageManager.kt`, lines 288 to 292:
  ```kotlin
  fun leaveSpace(spaceId: String): LeaveSpaceResponse {
      val response = apiClient.leaveSpace(LeaveSpaceRequest(spaceId, userId))
      spaceKeys.remove(spaceId)
      return response
  }
  ```

- **Java Environment Check**: `java -version` and `gradle --version` returned `CommandNotFoundException` on the host machine, meaning JUnit unit tests could not be compiled or run locally.

- **Python test execution**: Run command `python secure_space_app/tests/run_tests.py` ran successfully:
  ```
  Ran 60 tests in 3.302s
  OK
  ```
  All Python simulator E2E tests passed successfully.

---

## 2. Logic Chain

1. **Incorrect Peer Resolution in DM File Decryption**:
   - In 1-on-1 private messaging (DMs), the shared symmetric key is derived from the current user's private key and the peer's public key (e.g. `K_alice_bob`).
   - When Alice shares a file with Bob, she encrypts the file key under `K_alice_bob`.
   - When Bob (the recipient) attempts to download and decrypt the file, he calls `downloadAndDecryptFile` with `recipientId = "bob"`.
   - In `downloadAndDecryptFile`, because `spaceId` is null, the function resolves `peerId` as:
     `val peerId = if (recipientId == userId) recipientId else recipientId ...`
     Since `recipientId` is `"bob"` and Bob's `userId` is `"bob"`, `peerId` evaluates to `"bob"`.
   - The function retrieves Bob's public key using `getPeerPublicKey("bob")` and performs ECDH key agreement between Bob's private key and Bob's public key. This yields the self-derived shared key `K_bob_bob`.
   - Since `K_bob_bob != K_alice_bob`, the AES-GCM decryption of `encryptedFileKeyHex` will fail, causing a GCM authentication failure (throwing an `AEADBadTagException` at runtime).
   - Therefore, the recipient is unable to decrypt files shared with them in DMs.

2. **Redundant Logic**:
   - The expression `if (recipientId == userId) recipientId else recipientId` returns `recipientId` regardless of whether the condition is true or false. It serves no logical purpose and reflects copy-paste or parsing errors during implementation.

3. **Key Exposure in JVM Heap Memory**:
   - When a user leaves a space, `spaceKeys.remove(spaceId)` removes the entry from the client's map, but does not overwrite the bytes of the `ByteArray` containing the 256-bit symmetric key.
   - The secret key bytes linger in the heap memory until garbage collection occurs, exposing them to memory dump exploitation.

4. **Testing Coverage Gap**:
   - The Python test suite successfully verifies the Python `ClientSim` behavior. However, it does not execute the Kotlin classes (`MessageManager` or `CryptoEngine`).
   - Because the host lacks a Java JDK/Gradle compiler, the Kotlin unit tests (`MessageManagerTest.kt` and `CryptoEngineTest.kt`) were never executed, which allowed the cryptographic key agreement logic error to go unnoticed.

---

## 3. Caveats

- **No Compiler Verification**: We could not verify the syntax or execution of the Kotlin code under a real JVM compiler due to the lack of Java/Gradle on the host system. The findings are based on a static code review and dry-run analysis.

---

## 4. Conclusion

**Verdict: REQUEST_CHANGES**

The Kotlin implementation contains a **critical cryptographic defect** in file sharing decryption for DMs:
- The recipient resolves `peerId` to their own ID rather than the sender's, resulting in derivation of an incorrect ECDH shared key and subsequent GCM decryption failure.
- There are redundant logical expressions in the peer ID resolution.
- Key disposal does not securely zero-out secret keys in memory.
- There is a complete lack of JVM test execution in the E2E verification pipeline.

---

## 5. Verification Method

To verify the findings once the JDK/Gradle environment is available:
1. Navigate to `secure_space_app/client/`
2. Run `./gradlew test` (or `gradle test`).
3. The unit test `testUnitFileSharing` will fail with a GCM decryption error (e.g. `javax.crypto.AEADBadTagException: Tag mismatch`).

To fix the peer resolution issue, the method signature of `downloadAndDecryptFile` should be updated to receive the sender's ID, or the caller should pass the sender's ID as `recipientId` to allow deriving the correct key, or `downloadAndDecryptFile` should take the peer's ID directly. Additionally, `Arrays.fill` should be used to zero-out discarded space keys.

---

## Quality Review Report

**Verdict**: REQUEST_CHANGES

### Critical Finding 1: Key Agreement Peer Resolution Bug in DM File Decryption
- **What**: The recipient resolves the peer ID to their own ID instead of the sender's ID during DM file decryption.
- **Where**: `secure_space_app/client/app/src/main/java/com/secure/space/MessageManager.kt` (line 276)
- **Why**: Bob (recipient) attempts to decrypt the file key using a shared key derived with his own public key (`K_bob_bob`) rather than the sender's public key (`K_alice_bob`), causing AES-GCM decryption to throw an exception.
- **Suggestion**: Change `downloadAndDecryptFile` signature to take `peerId` (representing the other party in the DM) instead of `recipientId`, and update `MessageManagerTest.kt` line 206 to pass the sender's user ID (e.g. `"alice"`) to Bob's download call.

### Minor Finding 2: Redundant Ternary Expression
- **What**: Redundant `if-else` statement returning the same variable in both branches.
- **Where**: `secure_space_app/client/app/src/main/java/com/secure/space/MessageManager.kt` (line 276)
- **Why**: `if (recipientId == userId) recipientId else recipientId` is redundant and confusing.
- **Suggestion**: Simplify or fix the logic to correctly distinguish sender and recipient.

### Major Finding 3: Lack of Secure Erasure of Cryptographic Keys
- **What**: Leaving space keys in heap memory without zeroing them out.
- **Where**: `secure_space_app/client/app/src/main/java/com/secure/space/MessageManager.kt` (line 290)
- **Why**: Discarded space keys are removed from the map but remain in memory, creating a memory leak of cleartext secrets.
- **Suggestion**: Call `java.util.Arrays.fill(spaceKey, 0.toByte())` before removing the key from the map.

---

## Adversarial Review Report

**Overall risk assessment**: HIGH

### High Challenge 1: Key Agreement Failures in File Decryption
- **Assumption challenged**: That the recipient can decrypt files shared with them in DMs.
- **Attack scenario**: Alice shares an encrypted file with Bob. Bob downloads the file but is unable to decrypt it because the client derives the key using Bob's own public key instead of Alice's.
- **Blast radius**: Entire DM file sharing feature is broken and completely unusable for recipients.
- **Mitigation**: Pass the correct peer ID to key agreement.

### Medium Challenge 2: Heap memory exposure of cryptographic keys
- **Assumption challenged**: That removing space keys from the map secures the keys after leaving a space.
- **Attack scenario**: A user leaves a space, and an adversary obtains a heap dump of the device. The space key remains in plaintext inside the heap memory despite leaving the space.
- **Blast radius**: Retrospective decryption of space messages if the user's device is compromised after leaving a space.
- **Mitigation**: Use `Arrays.fill` to overwrite the key array with zeros.
