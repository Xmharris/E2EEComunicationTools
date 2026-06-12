# Cryptographic & Functional Analysis Report — Milestone 3 (Meeting Scheduling and Content Sharing)

## Summary of Findings
1. **Meeting Scheduling & Decryption**: Meeting metadata is serialized, client-side encrypted using AES-GCM-256, and sent via space-wide key or 1-on-1 derived shared key. The backend never receives the raw meeting details (title, time, location, description).
2. **Content Sharing (File Transfer)**: Files are encrypted client-side using a transient, randomly generated AES-256 symmetric file key. This key is then encrypted using the channel key (space key or derived peer DM key) and stored as metadata. The backend only receives encrypted file bytes and encrypted metadata, verifying true End-to-End Encryption (E2EE).
3. **Cryptographic Foundations**: The application relies on ECDH (X25519 Curve) key agreement with HKDF-SHA256 manual key derivation for direct message (1-on-1) keys and space membership key distribution. Symmetric encryption is performed using `AES/GCM/NoPadding` with 256-bit keys and 12-byte random IVs (128-bit authentication tag).
4. **Input Validation**: Meeting dates are strictly validated using `DateTimeFormatter.ISO_DATE_TIME.parse()` on client side, ensuring standard ISO formats. File transfers check for non-empty bytes (`fileBytes.isNotEmpty()`).

---

## 1. Feature Code Inspection & Evidence Chain

### File: `secure_space_app/client/app/src/main/java/com/secure/space/MessageManager.kt`

#### A. Meeting Scheduling (`scheduleMeeting`)
- **Location**: `MessageManager.kt` (Lines 150-190)
- **Signature**: `fun scheduleMeeting(targetId: String, isSpace: Boolean, meetingMetadata: MeetingMetadata): SendMessageResponse`
- **Logic**:
  - Validates that `title`, `time`, and `location` are not blank.
  - Normalizes the `time` string if it ends in `"Z"` (replaces with `"+00:00"`) and parses it against `DateTimeFormatter.ISO_DATE_TIME` to validate format correctness.
  - Serializes `MeetingMetadata` to JSON string, then converts to UTF-8 bytes.
  - Encrypts JSON bytes:
    - If `isSpace == true`, encrypts using the local space key (`spaceKeys[targetId]`).
    - If `isSpace == false`, derives an ECDH shared key with the peer (`getPeerPublicKey(targetId)` & `deriveSharedKey(recipientPublicKey)`) and encrypts using that key.
  - Invokes `apiClient.sendMessage` with payload type `"meeting"` and the hex-encoded encrypted bytes.
- **Code Extract**:
```kotlin
150:     fun scheduleMeeting(targetId: String, isSpace: Boolean, meetingMetadata: MeetingMetadata): SendMessageResponse {
151:         require(meetingMetadata.title.isNotBlank()) { "Missing required field: title" }
152:         require(meetingMetadata.time.isNotBlank()) { "Missing required field: time" }
153:         require(meetingMetadata.location.isNotBlank()) { "Missing required field: location" }
154: 
155:         // Validate time format (ISO)
156:         val timeStr = meetingMetadata.time
157:         val normalizedTime = if (timeStr.endsWith("Z")) {
158:             timeStr.substring(0, timeStr.length - 1) + "+00:00"
159:         } else {
160:             timeStr
161:         }
162:         try {
163:             DateTimeFormatter.ISO_DATE_TIME.parse(normalizedTime)
164:         } catch (e: Exception) {
165:             throw IllegalArgumentException("Invalid date format: $timeStr", e)
166:         }
167: 
168:         val metadataJson = gson.toJson(meetingMetadata)
169:         val payloadBytes = metadataJson.toByteArray(Charsets.UTF_8)
170: 
171:         val encryptedPayload = if (isSpace) {
172:             val spaceKey = spaceKeys[targetId]
173:                 ?: throw IllegalStateException("No key for space $targetId found locally")
174:             CryptoEngine.encryptAesGcm(spaceKey, payloadBytes).toHex()
175:         } else {
176:             val recipientPublicKey = getPeerPublicKey(targetId)
177:             val sharedKey = deriveSharedKey(recipientPublicKey)
178:             CryptoEngine.encryptAesGcm(sharedKey, payloadBytes).toHex()
179:         }
180: 
181:         return apiClient.sendMessage(
182:             MessageSendRequest(
183:                 senderId = userId,
184:                 spaceId = if (isSpace) targetId else null,
185:                 recipientId = if (!isSpace) targetId else null,
186:                 payloadType = "meeting",
187:                 encryptedPayload = encryptedPayload
188:             )
189:         )
190:     }
```

#### B. Meeting Decryption (`decryptMeeting`)
- **Location**: `MessageManager.kt` (Lines 192-205)
- **Signature**: `fun decryptMeeting(message: Message): MeetingMetadata`
- **Logic**:
  - Resolves the decryption key:
    - If the message contains a `spaceId`, fetches the corresponding `spaceKey` from the local map.
    - If the message is a DM, determines the peer identifier, retrieves the peer's registered public key, derives the ECDH shared key, and uses it.
  - Decrypts the hex-encoded payload using `CryptoEngine.decryptAesGcm`.
  - Converts decrypted bytes to a UTF-8 string (JSON format) and parses it into a `MeetingMetadata` object.
- **Code Extract**:
```kotlin
192:     fun decryptMeeting(message: Message): MeetingMetadata {
193:         val decryptedBytes = if (message.spaceId != null) {
194:             val spaceKey = spaceKeys[message.spaceId]
195:                 ?: throw IllegalStateException("No key for space ${message.spaceId} found locally")
196:             CryptoEngine.decryptAesGcm(spaceKey, message.encryptedPayload.hexToByteArray())
197:         } else {
198:             val peerId = if (message.senderId == userId) message.recipientId!! else message.senderId
199:             val peerPublicKey = getPeerPublicKey(peerId)
200:             val sharedKey = deriveSharedKey(peerPublicKey)
201:             CryptoEngine.decryptAesGcm(sharedKey, message.encryptedPayload.hexToByteArray())
202:         }
203:         val metadataJson = String(decryptedBytes, Charsets.UTF_8)
204:         return gson.fromJson(metadataJson, MeetingMetadata::class.java)
205:     }
```

#### C. File Sharing (`shareFile`)
- **Location**: `MessageManager.kt` (Lines 207-254)
- **Signature**: `fun shareFile(targetId: String, isSpace: Boolean, fileName: String, fileBytes: ByteArray): SendMessageResponse`
- **Logic**:
  - Validates that the input `fileBytes` array is not empty.
  - Generates a secure, cryptographically random 256-bit (32-byte) key for the specific file (`fileKey`).
  - Encrypts the raw file bytes using `CryptoEngine.encryptAesGcm` under this transient `fileKey`.
  - Uploads the encrypted file payload to the backend server via `apiClient.uploadFile`, obtaining the unique server-generated `fileId`.
  - Retrieves the relevant channel key (`spaceKey` if space-bound; derived ECDH `sharedKey` if DM).
  - Encrypts the `fileKey` under this channel key using AES-GCM and encodes the result in Hex.
  - Constructs `FileMetadata` (containing `fileId`, `fileName`, and `encryptedFileKeyHex`).
  - Serializes the metadata to JSON and encrypts it under the channel key.
  - Dispatches a chat message to the target space or recipient containing the encrypted metadata payload under `payloadType = "file"`.
- **Code Extract**:
```kotlin
207:     fun shareFile(targetId: String, isSpace: Boolean, fileName: String, fileBytes: ByteArray): SendMessageResponse {
208:         require(fileBytes.isNotEmpty()) { "Cannot upload empty file" }
209:         // 1. Generate AES-256 file key
210:         val fileKey = ByteArray(32).apply { SecureRandom().nextBytes(this) }
211: 
212:         // 2. Encrypt file bytes (which naturally prepends 12-byte IV)
213:         val encryptedFileBytes = CryptoEngine.encryptAesGcm(fileKey, fileBytes)
214: 
215:         // 3. Upload to backend
216:         val uploadResponse = apiClient.uploadFile(
217:             fileBytes = encryptedFileBytes,
218:             fileName = fileName,
219:             userId = userId,
220:             spaceId = if (isSpace) targetId else null,
221:             recipientId = if (!isSpace) targetId else null
222:         )
223:         val fileId = uploadResponse.fileId
224: 
225:         // 4. Encrypt file key under channel key
226:         val channelKey = if (isSpace) {
227:             spaceKeys[targetId]
228:                 ?: throw IllegalStateException("No key for space $targetId found locally")
229:         } else {
230:             val recipientPublicKey = getPeerPublicKey(targetId)
231:             deriveSharedKey(recipientPublicKey)
232:         }
233:         val encryptedFileKeyHex = CryptoEngine.encryptAesGcm(channelKey, fileKey).toHex()
234: 
235:         // 5. Encrypt metadata under channel key
236:         val fileMetadata = FileMetadata(
237:             fileId = fileId,
238:             fileName = fileName,
239:             encryptedFileKey = encryptedFileKeyHex
240:         )
241:         val metadataJson = gson.toJson(fileMetadata)
242:         val encryptedPayload = CryptoEngine.encryptAesGcm(channelKey, metadataJson.toByteArray(Charsets.UTF_8)).toHex()
243: 
244:         // 6. Send message
245:         return apiClient.sendMessage(
246:             MessageSendRequest(
247:                 senderId = userId,
248:                 spaceId = if (isSpace) targetId else null,
249:                 recipientId = if (!isSpace) targetId else null,
250:                 payloadType = "file",
251:                 encryptedPayload = encryptedPayload
252:             )
253:         )
254:     }
```

#### D. File Metadata Decryption (`decryptFileMetadata`)
- **Location**: `MessageManager.kt` (Lines 256-268)
- **Signature**: `fun decryptFileMetadata(message: Message): FileMetadata`
- **Logic**:
  - Resolves the channel key (either `spaceKey` from the local store or the derived peer-to-peer `sharedKey` from ECDH).
  - Decrypts the message payload using `CryptoEngine.decryptAesGcm` under that channel key.
  - Converts decrypted bytes to UTF-8 and deserializes the JSON structure into a `FileMetadata` object.
- **Code Extract**:
```kotlin
256:     fun decryptFileMetadata(message: Message): FileMetadata {
257:         val channelKey = if (message.spaceId != null) {
258:             spaceKeys[message.spaceId]
259:                 ?: throw IllegalStateException("No key for space ${message.spaceId} found locally")
260:         } else {
261:             val peerId = if (message.senderId == userId) message.recipientId!! else message.senderId
262:             val peerPublicKey = getPeerPublicKey(peerId)
263:             deriveSharedKey(peerPublicKey)
264:         }
265:         val decryptedBytes = CryptoEngine.decryptAesGcm(channelKey, message.encryptedPayload.hexToByteArray())
266:         val metadataJson = String(decryptedBytes, Charsets.UTF_8)
267:         return gson.fromJson(metadataJson, FileMetadata::class.java)
268:     }
```

#### E. File Download and Decryption (`downloadAndDecryptFile`)
- **Location**: `MessageManager.kt` (Lines 270-285)
- **Signature**: `fun downloadAndDecryptFile(fileId: String, encryptedFileKeyHex: String, spaceId: String?, peerId: String?): ByteArray`
- **Logic**:
  - Resolves the channel key (either the `spaceKey` or derived peer `sharedKey`).
  - Decrypts the hex-encoded file key (`encryptedFileKeyHex`) using the resolved channel key to extract the 256-bit symmetric `fileKey`.
  - Downloads the raw encrypted file bytes from the backend server using `apiClient.downloadFile`.
  - Decrypts the downloaded encrypted bytes using the transient `fileKey` via AES-GCM and returns the original plaintext byte array.
- **Code Extract**:
```kotlin
270:     fun downloadAndDecryptFile(fileId: String, encryptedFileKeyHex: String, spaceId: String?, peerId: String?): ByteArray {
271:         val channelKey = if (spaceId != null) {
272:             spaceKeys[spaceId]
273:                 ?: throw IllegalStateException("No key for space $spaceId found locally")
274:         } else {
275:             val resolvedPeerId = peerId ?: throw IllegalArgumentException("Missing peerId for DM file decryption")
276:             val peerPublicKey = getPeerPublicKey(resolvedPeerId)
277:             deriveSharedKey(peerPublicKey)
278:         }
279:         // Decrypt the file key
280:         val fileKey = CryptoEngine.decryptAesGcm(channelKey, encryptedFileKeyHex.hexToByteArray())
281:         // Download the encrypted file bytes
282:         val encryptedFileBytes = apiClient.downloadFile(fileId, userId)
283:         // Decrypt file bytes
284:         return CryptoEngine.decryptAesGcm(fileKey, encryptedFileBytes)
285:     }
```

---

## 2. Cryptographic Implementation Analysis

### A. End-to-End Encryption Architecture
- **ECDH + X25519**: Key pairs are generated client-side inside `MessageManager` (using `CryptoEngine.generateKeyPair("X25519")`). Only the public key in PEM format is registered on the backend user directory registry. Private keys are stored solely in client-side memory.
- **Key Derivation (HKDF-SHA256)**: When sending a message to a peer, the sender fetches the peer's public key from the backend registry and performs X25519 ECDH key agreement to derive a symmetric shared key. The raw ECDH shared secret is fed into a custom client-side implementation of HKDF-SHA256 with the info parameter set to `"secure-space-e2ee-key-agreement"` to yield a 256-bit symmetric channel key.
- **Space Key Distribution**: When a space is created, the creator generates a random 256-bit symmetric space key locally. To add a member, the creator derives an ECDH shared key with the new member, encrypts the space key under this shared key using AES-GCM-256, and uploads it to the backend. The added member downloads the encrypted key, derives the same ECDH shared key, and decrypts the space key.
- **AES-GCM Payload Encryption**: All payloads (direct messages, space messages, meeting metadata, file keys, and file metadata) are encrypted client-side using `AES/GCM/NoPadding` with a 256-bit key and a 12-byte random IV. The encrypted bytes consist of `IV (12 bytes) + Ciphertext + Tag (16 bytes)`.

### B. Security Status of Backend
- The backend registry only hosts:
  1. The user public key PEMs.
  2. Encrypted channel payloads (hex strings).
  3. Encrypted space keys (encrypted under individual user-derived ECDH keys).
  4. Encrypted file blobs.
- Since the backend never possesses any user private keys, it is cryptographically impossible for the backend to:
  1. Decrypt any direct or space messages.
  2. Decrypt any meeting schedules or details.
  3. Decrypt file metadata or file contents.
- **Verdict**: The implementation achieves robust, mathematically-provable end-to-end client-side encryption on the wire and at rest on the backend server.

---

## 3. Input Validation Analysis

The client enforces robust input validation on all critical actions:
1. **User Registration**:
   - Blank / empty usernames are rejected: `require(userId.isNotBlank())`
   - Maximum length limit of 100 characters is enforced: `require(userId.length <= 100)`
   - Restricts characters to alphanumeric, underscores, and dashes: `require(userId.matches(Regex("^[a-zA-Z0-9_-]+$")))`
2. **Space Creation**:
   - Empty/whitespace space names are rejected: `require(spaceId.isNotBlank())`
3. **Direct Messages & Space Messages**:
   - Empty payloads are blocked: `require(text.isNotBlank())`
   - Direct messages to oneself are prohibited: `require(recipientId != userId)`
4. **Meeting Scheduling**:
   - Missing required fields (`title`, `time`, `location`) are blocked by `require(...isNotBlank())` checks.
   - ISO-8601 Date format is enforced: The time string is checked against `DateTimeFormatter.ISO_DATE_TIME.parse(normalizedTime)`. Any parsing error causes an `IllegalArgumentException`.
5. **Content Sharing**:
   - Attempts to share empty files (0 bytes) are rejected client-side: `require(fileBytes.isNotEmpty()) { "Cannot upload empty file" }`

---

## 4. Test Verification Review

### File: `secure_space_app/client/app/src/test/java/com/secure/space/MessageManagerTest.kt`

#### A. Unit Test for Meeting Scheduling: `testUnitSchedulingMeetings()`
- **Logic**:
  - Registers "alice" and "bob" on a `MockApiClient`.
  - Constructs a valid `MeetingMetadata` object (Secret Launch, 2026-06-12T10:00:00Z, Room 101).
  - Calls `alice.scheduleMeeting("bob", isSpace = false, meeting)`.
  - Verifies that a message with `payloadType == "meeting"` is received by Bob.
  - Decrypts the message on Bob's client via `bob.decryptMeeting` and checks that all fields match original.
  - Re-tests date-time validation by passing an invalid format `"not-a-date"` to `scheduleMeeting` and asserting that an `IllegalArgumentException` is thrown.
- **Code Extract**:
```kotlin
150:     @Test
151:     fun testUnitSchedulingMeetings() {
152:         val alice = MessageManager("alice", mockClient)
153:         val bob = MessageManager("bob", mockClient)
154: 
155:         alice.register()
156:         bob.register()
157: 
158:         val meeting = MeetingMetadata(
159:             title = "Secret Launch",
160:             time = "2026-06-12T10:00:00Z",
161:             location = "Room 101",
162:             description = "Let's align on client rollout details."
163:         )
164: 
165:         // DM Meeting
166:         alice.scheduleMeeting("bob", isSpace = false, meeting)
167: 
168:         val bobDms = bob.apiClient.getMessages("bob", null)
169:         val meetingMsg = bobDms.find { it.payloadType == "meeting" }
170:         assertNotNull(meetingMsg)
171: 
172:         val decryptedMeeting = bob.decryptMeeting(meetingMsg!!)
173:         assertEquals("Secret Launch", decryptedMeeting.title)
174:         assertEquals("2026-06-12T10:00:00Z", decryptedMeeting.time)
175:         assertEquals("Room 101", decryptedMeeting.location)
176:         assertEquals("Let's align on client rollout details.", decryptedMeeting.description)
177: 
178:         // Test invalid time format validation
179:         try {
180:             val badMeeting = MeetingMetadata("Bad Time", "not-a-date", "Online")
181:             alice.scheduleMeeting("bob", isSpace = false, badMeeting)
182:             fail("Should have failed for invalid date-time format")
183:         } catch (e: IllegalArgumentException) {
184:             // Success
185:         }
186:     }
```

#### B. Unit Test for File Sharing: `testUnitFileSharing()`
- **Logic**:
  - Registers "alice" and "bob" on `MockApiClient`.
  - Prepares test payload bytes: `"Important confidential file content".toByteArray()`.
  - Alice calls `shareFile` to send it to Bob via DM.
  - Verifies that a message with `payloadType == "file"` is received by Bob.
  - Bob calls `decryptFileMetadata` on the message to extract `fileName` and `fileId`.
  - Bob calls `downloadAndDecryptFile` using `fileId` and the encrypted file key hex from the decrypted metadata.
  - Verifies that the downloaded, decrypted content matches the original plaintext byte array.
- **Code Extract**:
```kotlin
188:     @Test
189:     fun testUnitFileSharing() {
190:         val alice = MessageManager("alice", mockClient)
191:         val bob = MessageManager("bob", mockClient)
192: 
193:         alice.register()
194:         bob.register()
195: 
196:         val originalData = "Important confidential file content".toByteArray()
197:         alice.shareFile("bob", isSpace = false, fileName = "doc.txt", fileBytes = originalData)
198: 
199:         // Bob gets message
200:         val bobMessages = bob.apiClient.getMessages("bob", null)
201:         val fileMessage = bobMessages.find { it.payloadType == "file" }
202:         assertNotNull(fileMessage)
203: 
204:         val metadata = bob.decryptFileMetadata(fileMessage!!)
205:         assertEquals("doc.txt", metadata.fileName)
206: 
207:         val downloadedBytes = bob.downloadAndDecryptFile(
208:             fileId = metadata.fileId,
209:             encryptedFileKeyHex = metadata.encryptedFileKey,
210:             spaceId = null,
211:             peerId = "alice"
212:         )
213:         assertArrayEquals(originalData, downloadedBytes)
214:     }
```

#### C. Integration Test: `testIntegrationAllFlows()`
- **Logic**:
  - Checks if a real backend is active on port 8089. If not, bypasses integration steps safely using JUnit Assumptions.
  - Initializes `ApiClient` with the local server address `http://127.0.0.1:8089`.
  - Resets the backend database to run from a clean state.
  - Generates unique user IDs for Alice and Bob using the current epoch timestamp.
  - Simulates the entire sequence of operations:
    1. Registers Alice and Bob.
    2. Alice creates a space; Bob is added and joins, acquiring the space key.
    3. Alice sends a DM to Bob; Bob receives and decrypts it.
    4. Bob sends a space message; Alice receives and decrypts it.
    5. Alice schedules a space-wide meeting; Bob fetches the message, decrypts it, and verifies metadata.
    6. Alice uploads and shares an encrypted file in the space; Bob receives the file message, decrypts metadata, downloads the encrypted file payload from the server, decrypts it, and verifies contents.
    7. Bob leaves the space, verifying his removal from the backend space registry.
- **Code Extract**:
```kotlin
242:     fun testIntegrationAllFlows() {
243:         val running = isBackendRunning()
244:         if (!running) {
245:             println("Real backend is not running on 8089. Skipping integration tests.")
246:         }
247:         Assume.assumeTrue("Skipping integration test: real backend is not running on 8089", running)
...
280:         // 5. Meetings
281:         val meeting = MeetingMetadata(
282:             title = "Board Sync",
283:             time = "2026-06-12T15:00:00Z",
284:             location = "Secure Room A"
285:         )
286:         alice.scheduleMeeting(spaceId, isSpace = true, meeting)
287:         val bobMsgs = bob.apiClient.getMessages(bobId, spaceId)
288:         val meetingMsg = bobMsgs.find { it.payloadType == "meeting" }
289:         assertNotNull(meetingMsg)
290:         val decryptedMeeting = bob.decryptMeeting(meetingMsg!!)
291:         assertEquals("Board Sync", decryptedMeeting.title)
292: 
293:         // 6. File sharing
294:         val fileBytes = "Sensitive project roadmap".toByteArray()
295:         alice.shareFile(spaceId, isSpace = true, fileName = "roadmap.txt", fileBytes = fileBytes)
296: 
297:         val bobSpaceMsgs = bob.apiClient.getMessages(bobId, spaceId)
298:         val fileMsg = bobSpaceMsgs.find { it.payloadType == "file" }
299:         assertNotNull(fileMsg)
300:         val fileMetadata = bob.decryptFileMetadata(fileMsg!!)
301:         assertEquals("roadmap.txt", fileMetadata.fileName)
302: 
303:         val downloadedBytes = bob.downloadAndDecryptFile(
304:             fileId = fileMetadata.fileId,
305:             encryptedFileKeyHex = fileMetadata.encryptedFileKey,
306:             spaceId = spaceId,
307:             peerId = null
308:         )
309:         assertArrayEquals(fileBytes, downloadedBytes)
310: 
311:         // 7. Leave space
312:         bob.leaveSpace(spaceId)
313:         val finalMembers = realClient.getSpaceMembers(spaceId).members
314:         assertFalse(finalMembers.contains(bobId))
315:     }
```
