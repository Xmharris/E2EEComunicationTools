# Milestone 3 Explorer Analysis: Meeting Scheduling and Content Sharing

## Executive Summary
This analysis details the evaluation of the meeting scheduling and content sharing (file transfer) features in the End-to-End Encrypted (E2EE) Secure Space Application. The application employs client-side X25519 (ECDH) key agreement, HKDF-SHA256 key derivation, and AES-GCM (256-bit) encryption for securing all data payloads (text, meetings, and file metadata/data) client-side before transmission. The backend acts as a zero-knowledge directory and relay, never receiving or holding private keys or plaintext payloads. This report outlines the code structure, cryptographic architecture, input validation mechanisms, and test coverage.

---

## 1. Inspection of Core Features (`MessageManager.kt`)

The core scheduling and content sharing methods are defined in `secure_space_app/client/app/src/main/java/com/secure/space/MessageManager.kt`. 

### A. Meeting Scheduling (`scheduleMeeting` and `decryptMeeting`)
* **`scheduleMeeting` (lines 150-190)**:
  * **Signature**: `fun scheduleMeeting(targetId: String, isSpace: Boolean, meetingMetadata: MeetingMetadata): SendMessageResponse`
  * **Input Validation**: Enforces non-blank fields for `title`, `time`, and `location` using `require()`. Enforces ISO 8601 date-time format for the `time` field using `DateTimeFormatter.ISO_DATE_TIME.parse()`.
  * **Symmetric Encryption**: 
    * If `isSpace == true`, encrypts the meeting metadata using the space-specific key (`spaceKeys[targetId]`).
    * If `isSpace == false` (DM), derives a shared key using ECDH key agreement with the recipient's public key (`deriveSharedKey(recipientPublicKey)`) and encrypts the payload.
    * Both encryption paths utilize `CryptoEngine.encryptAesGcm()`, producing a combined `IV + ciphertext + authentication tag` byte array, which is converted to hex.
  * **API Call**: Sends a `MessageSendRequest` to the backend with `payloadType = "meeting"` and the encrypted payload.
* **`decryptMeeting` (lines 192-205)**:
  * **Signature**: `fun decryptMeeting(message: Message): MeetingMetadata`
  * **Decryption Logic**:
    * If `message.spaceId != null`, decrypts using the local space key.
    * If `message.spaceId == null` (DM), resolves the peer ID, fetches their public key, derives the ECDH shared key, and decrypts the payload.
    * Uses `CryptoEngine.decryptAesGcm()` to decrypt the hex-encoded payload.
    * Deserializes the decrypted UTF-8 JSON bytes back into a `MeetingMetadata` object.

### B. Content Sharing / File Transfer (`shareFile`, `decryptFileMetadata`, and `downloadAndDecryptFile`)
* **`shareFile` (lines 207-254)**:
  * **Signature**: `fun shareFile(targetId: String, isSpace: Boolean, fileName: String, fileBytes: ByteArray): SendMessageResponse`
  * **Validation**: Restricts empty uploads: `require(fileBytes.isNotEmpty()) { "Cannot upload empty file" }`.
  * **Two-Layer Cryptography**:
    1. **File Encryption**: Generates a cryptographically secure, random 256-bit (32 bytes) symmetric key (`fileKey`). Encrypts the raw file bytes using `CryptoEngine.encryptAesGcm(fileKey, fileBytes)`.
    2. **Upload**: Uploads the encrypted file bytes to the backend via `apiClient.uploadFile`, receiving a `fileId`.
    3. **Key Encryption**: Encrypts the `fileKey` under the channel/destination key (either `spaceKey` or ECDH `sharedKey` for the recipient).
    4. **Metadata Encryption**: Bundles the `fileId`, `fileName`, and the encrypted file key into a `FileMetadata` object. Serializes and encrypts this metadata object under the channel key.
    5. **Message Relay**: Sends a message of type `file` with the encrypted metadata payload to the backend.
* **`decryptFileMetadata` (lines 256-268)**:
  * **Signature**: `fun decryptFileMetadata(message: Message): FileMetadata`
  * **Decryption Logic**: Decrypts the message's `encryptedPayload` (containing serialized metadata) using the destination channel key (`spaceKey` or ECDH `sharedKey`), returning the `FileMetadata` object.
* **`downloadAndDecryptFile` (lines 270-285)**:
  * **Signature**: `fun downloadAndDecryptFile(fileId: String, encryptedFileKeyHex: String, spaceId: String?, peerId: String?): ByteArray`
  * **Decryption Logic**:
    1. Retrieves/derives the destination channel key (`spaceKey` or ECDH `sharedKey`).
    2. Decrypts `encryptedFileKeyHex` using the channel key to retrieve the 256-bit `fileKey`.
    3. Downloads the encrypted file bytes from the backend via `apiClient.downloadFile()`.
    4. Decrypts the file bytes using `fileKey` via `CryptoEngine.decryptAesGcm()`.

---

## 2. Cryptographic Architecture & Implementation Analysis

### A. End-to-End Client-Side Encryption (E2EE)
* **Key Agreement (ECDH)**: The client application generates X25519 key pairs (`CryptoEngine.generateKeyPair("X25519")`) on initialization. The private key remains in client memory and is never transmitted.
* **Key Derivation (HKDF)**: Derived keys are created via a manual implementation of HKDF-SHA256 (RFC 5869) on top of standard HMAC-SHA256 (`CryptoEngine.deriveSharedKey` lines 83-100). The derivation uses salt=null (defaulting to 32 zero bytes) and the application-specific info context `"secure-space-e2ee-key-agreement"`.
* **Symmetric Encryption (AES-GCM)**: All message payloads and raw files are encrypted using AES-GCM (256-bit key length, 12-byte random IV, 128-bit authentication tag). The 12-byte IV is prepended to the ciphertext before transmission (`CryptoEngine.encryptAesGcm` lines 148-164).
* **Space/Channel Isolation**: Spaces use random 256-bit symmetric keys generated by the creator. These keys are distributed to other members by encrypting them under their mutual ECDH shared keys. Storing the encrypted space keys on the backend allows new members to join asynchronously while keeping the plaintext keys inaccessible to the server.
* **File Encryption Isolation**: Files are encrypted with unique, ephemeral random 256-bit keys (`fileKey`). Even if a space key is somehow compromised, it only exposes the file keys of the files shared in that space, rather than a master key.

### B. Backend Knowledge Profile
The backend database schema (`main.py` lines 23-60) stores only:
* `users`: `user_id` (text), `public_key` (text)
* `spaces`: `space_id` (text), `creator_id` (text)
* `space_keys`: `space_id` (text), `user_id` (text), `encrypted_key` (text)
* `messages`: `id` (int), `sender_id` (text), `recipient_id` (text), `space_id` (text), `payload_type` (text), `encrypted_payload` (text)
* `files`: `file_id` (text), `file_bytes` (blob), `user_id` (text), `space_id` (text), `recipient_id` (text)

Since the backend stores only encrypted payloads, encrypted space keys, and public keys, it has zero ability to decrypt any text, meeting information, or files.

---

## 3. Robust Input Validation Assessment

The client and backend enforce rigorous validation constraints at key boundaries:

| Entity | Validation Target | Code Location | Rule & Action |
|---|---|---|---|
| **User Registration** | Empty username | `MessageManager.kt:40` | `require(userId.isNotBlank())` -> `IllegalArgumentException` |
| **User Registration** | Username length | `MessageManager.kt:41` | `require(userId.length <= 100)` -> `IllegalArgumentException` |
| **User Registration** | Special characters | `MessageManager.kt:42` | Enforces regex `^[a-zA-Z0-9_-]+$` -> `IllegalArgumentException` |
| **Space Management** | Empty Space ID | `MessageManager.kt:63` | `require(spaceId.isNotBlank())` -> `IllegalArgumentException` |
| **Direct Messaging** | Self Messaging | `MessageManager.kt:92` | `require(recipientId != userId)` -> `IllegalArgumentException` |
| **Direct Messaging** | Empty Message | `MessageManager.kt:91`, `123` | `require(text.isNotBlank())` -> `IllegalArgumentException` |
| **Meeting Scheduling** | Missing fields | `MessageManager.kt:151-153` | Checks title, time, location are not blank -> `IllegalArgumentException` |
| **Meeting Scheduling** | Invalid date format | `MessageManager.kt:156-166` | Formats and parses via `DateTimeFormatter.ISO_DATE_TIME.parse()` -> `IllegalArgumentException` |
| **Content Sharing** | Empty file upload | `MessageManager.kt:208` | `require(fileBytes.isNotEmpty())` -> `IllegalArgumentException` |
| **Content Sharing** | DM file decryption | `MessageManager.kt:275` | `require(resolvedPeerId != null)` -> `IllegalArgumentException` |

---

## 4. Test Coverage Verification

The codebase includes two primary test suites covering scheduling and sharing flows:

### A. Kotlin JVM Unit Tests (`MessageManagerTest.kt`)
* **`testUnitSchedulingMeetings()` (lines 150-186)**:
  * Schedules a mock meeting between Alice and Bob via DM.
  * Asserts the meeting message is correctly produced on the mock client.
  * Decrypts the message and asserts that all fields (`title`, `time`, `location`, `description`) match the original.
  * Asserts that passing an invalid date format (`"not-a-date"`) successfully throws an `IllegalArgumentException`.
* **`testUnitFileSharing()` (lines 187-213)**:
  * Shares a mock file ("doc.txt") with content `Important confidential file content` from Alice to Bob.
  * Asserts the file message is posted.
  * Decrypts file metadata and downloads/decrypts the file.
  * Asserts that the decrypted byte array matches the original.
* **`testIntegrationAllFlows()` (lines 242-314)**:
  * Performs integration tests against the real database-backed backend (if running).
  * Validates registration, space setup, DM, space messaging, space meeting scheduling, space file sharing (upload/download/decryption), and space leaving.

### B. Python E2E Test Suite (`test_e2e_suite.py`)
Includes parallel E2E verification of identical cryptographic flows:
* `test_schedule_meeting_in_space` / `test_schedule_meeting_in_dm`: Schedules meetings and decrypts metadata.
* `test_meeting_invalid_date_format`: Asserts rejection of non-ISO formats.
* `test_meeting_missing_required_fields`: Asserts rejection of incomplete payloads.
* `test_upload_file` / `test_download_file` / `test_share_file_in_space` / `test_share_file_in_dm`: Asserts file upload, download, metadata distribution, and decryption.
* `test_upload_empty_file`: Asserts that empty file uploads fail with `400 Bad Request`.
* `test_wire_level_encryption_verification`: Directly verifies that all message payloads in the backend database are encrypted (no plaintext leaks).
