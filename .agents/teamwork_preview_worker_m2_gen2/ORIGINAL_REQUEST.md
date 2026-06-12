## 2026-06-12T03:23:57Z
You are the teamwork_preview_worker subagent for Milestone 2 (Generation 2).
Your working directory is C:\Users\xavie\Documents\antigravity\quick-franklin\.agents\teamwork_preview_worker_m2_gen2\
Your task is to fix the cryptographic and schema bugs identified by the reviewers in the secure space Kotlin client code.

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Scope of work:
1. Modify `secure_space_app/client/app/src/main/java/com/secure/space/model/Models.kt`:
   - Remove the `iv: String` field from `FileMetadata` class to restore a strict 1:1 match with Python client simulator's schema.

2. Modify `secure_space_app/client/app/src/main/java/com/secure/space/MessageManager.kt`:
   - Update `shareFile` to instantiate `FileMetadata` without the `iv` field.
   - Update the signature of `downloadAndDecryptFile` to accept `peerId: String?` instead of `recipientId: String?`.
   - Update the implementation of `downloadAndDecryptFile` to use `peerId` to derive the shared key in case of DMs (when `spaceId` is null). For example:
     ```kotlin
     val channelKey = if (spaceId != null) {
         spaceKeys[spaceId]
             ?: throw IllegalStateException("No key for space $spaceId found locally")
     } else {
         val resolvedPeerId = peerId ?: throw IllegalArgumentException("Missing peerId for DM file decryption")
         val peerPublicKey = getPeerPublicKey(resolvedPeerId)
         deriveSharedKey(peerPublicKey)
     }
     ```

3. Modify `secure_space_app/client/app/src/test/java/com/secure/space/MessageManagerTest.kt`:
   - In `testUnitFileSharing`, update the call to `bob.downloadAndDecryptFile` to pass `peerId = "alice"` instead of `recipientId = "bob"`.
   - Also check the other unit/integration tests to ensure compatibility.

4. Environmental Check:
   - Search for a Java JDK (e.g. `java.exe` or `javac.exe`) or any JVM-compatible tools in standard directories on `C:\` (like `C:\Program Files\Java`, `C:\Program Files\Android\Android Studio\jbr`, `C:\Users\xavie\.gradle`, etc.). If found, temporarily add it to your PATH for compilation.
   - Try to compile the Kotlin project and run the tests to confirm there are no syntax/compilation errors.
   - Run the Python mock backend tests (`python secure_space_app/tests/run_tests.py`) to confirm that all 60 tests still pass successfully.

5. Write a detailed handoff.md report summarizing the changes made, build commands tried, and outcomes.
6. Notify the sub-orchestrator (conversation ID: 3942c01a-5f78-489c-8403-4de96aa1daa9) when finished.
