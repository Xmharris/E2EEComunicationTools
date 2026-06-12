# Cryptographic and Functional Exploration Report — Milestone 3 (Meeting Scheduling and Content Sharing)

## Executive Summary
This report analyzes the Kotlin client-side implementation of meeting scheduling and content sharing (file transfer) features in the Secure Space E2EE Application. The findings confirm that meeting details and shared files are fully encrypted end-to-end (E2EE) client-side before transmission or storage. Cryptographic key agreement utilizes ECDH (X25519) for direct channels, and pre-distributed symmetric keys for group spaces. Symmetrical encryption is implemented using AES-GCM-256. Robust input validations are enforced at key boundaries, including date-time syntax parsing and empty file prevention.

---

## 1. Codebase Exploration: Meeting Scheduling and Content Sharing

### 1.1 Meeting Scheduling Features in `MessageManager.kt`
- **`scheduleMeeting`** (Lines 150-190):
  - **Signature**: `fun scheduleMeeting(targetId: String, isSpace: Boolean, meetingMetadata: MeetingMetadata): SendMessageResponse`
  - **Inputs**: Target identifier (recipient or space ID), a boolean indicating if it is a space channel, and a `MeetingMetadata` data structure.
  - **Functionality**:
    1. Validates that the metadata fields `title`, `time`, and `location` are not blank.
    2. Validates the `time` string against the ISO-8601 standard (`DateTimeFormatter.ISO_DATE_TIME`), normalizing `Z` suffix to `+00:00`.
    3. Serializes the metadata to JSON using Gson.
    4. Encrypts the JSON string with AES-GCM. If `isSpace` is true, the local space key is retrieved from `spaceKeys`. If false, a shared key is derived with the recipient's public key via ECDH.
    5. Transmits the payload to the backend via `apiClient.sendMessage` with `payloadType = "meeting"`.

- **`decryptMeeting`** (Lines 192-205):
  - **Signature**: `fun decryptMeeting(message: Message): MeetingMetadata`
  - **Functionality**:
    1. Determines whether the meeting message belongs to a space (`message.spaceId != null`) or a direct message.
    2. Resolves the correct decryption key (the symmetric space key or the derived ECDH shared key).
    3. Decrypts the payload via `CryptoEngine.decryptAesGcm`.
    4. Deserializes the plaintext JSON string back into a `MeetingMetadata` object.

### 1.2 Content Sharing (File Transfer) Features in `MessageManager.kt`
- **`shareFile`** (Lines 207-254):
  - **Signature**: `fun shareFile(targetId: String, isSpace: Boolean, fileName: String, fileBytes: ByteArray): SendMessageResponse`
  - **Functionality**:
    1. Asserts that `fileBytes` is non-empty (`require(fileBytes.isNotEmpty())`).
    2. Generates an ephemeral 256-bit symmetric AES file key: `val fileKey = ByteArray(32).apply { SecureRandom().nextBytes(this) }`.
    3. Encrypts the raw file bytes with the generated `fileKey` using AES-GCM (automatically prepending the 12-byte IV).
    4. Uploads the encrypted file bytes, along with the filename, to the server using `apiClient.uploadFile`.
    5. Encrypts the ephemeral `fileKey` under the channel key (space key or ECDH shared key).
    6. Constructs a `FileMetadata` object consisting of the returned `fileId`, the `fileName`, and the hex-encoded encrypted file key.
    7. Serializes and encrypts this `FileMetadata` under the channel key, sending it as a message of `payloadType = "file"`.

- **`decryptFileMetadata`** (Lines 256-268):
  - **Signature**: `fun decryptFileMetadata(message: Message): FileMetadata`
  - **Functionality**:
    1. Resolves the channel key (space key or derived shared key).
    2. Decrypts the message payload and deserializes it into `FileMetadata` containing the `fileId` and the encrypted file key.

- **`downloadAndDecryptFile`** (Lines 270-285):
  - **Signature**: `fun downloadAndDecryptFile(fileId: String, encryptedFileKeyHex: String, spaceId: String?, peerId: String?): ByteArray`
  - **Functionality**:
    1. Resolves the channel key using either `spaceId` or `peerId`.
    2. Decrypts the encrypted file key hex using the resolved channel key.
    3. Downloads the encrypted file bytes from the backend using `apiClient.downloadFile`.
    4. Decrypts the file bytes using the decrypted file key via AES-GCM.

---

## 2. Cryptographic Architecture Analysis

### 2.1 End-to-End Encryption (E2EE) on the Wire
Both meeting details and files are fully encrypted client-side, ensuring zero-trust transport:
- **Key Agreement**: Direct message channels derive a shared key via ECDH (specifically `X25519` curve) using the client's local private key and the recipient's retrieved public key. This shared key is generated in memory using `CryptoEngine.deriveSharedKey` with a custom info parameter (`"secure-space-e2ee-key-agreement"`).
- **Symmetric Encryption**: Data payloads (text messages, meeting metadata, file contents, and file keys) are encrypted using AES-GCM (`AES/GCM/NoPadding`).
- **Private Key Isolation**: Clients generate their key pair locally upon instantiation:
  ```kotlin
  val keyPair: KeyPair = CryptoEngine.generateKeyPair("X25519")
  ```
  During registration, only the public key in PEM format is uploaded to the backend (`apiClient.registerUser(UserRegisterRequest(userId, publicKeyPem))`). The private key (`keyPair.private`) is never serialized or transmitted.
- **File Encryption Hierarchy**: To avoid encrypting large files with the long-term channel keys (which would expose the channel key to cryptanalysis under large volumes of data), the system generates an ephemeral symmetric key (`fileKey`) per file. This file key is encrypted with the channel key, and the file content is encrypted with the file key, representing a standard cryptographic envelope format.

### 2.2 Verification of Backend Trust Boundary
The backend stores:
1. Public key PEMs associated with `userId`.
2. Encrypted message payloads (meeting JSON metadata is stored inside `encryptedPayload` as a hex-encoded string).
3. Encrypted space keys distributed to space members (encrypted under the member's ECDH shared key).
4. Encrypted file blobs identified by UUIDs.
Since the backend does not possess any private keys or raw space keys, it cannot decrypt any message payloads, meeting details, file keys, or file bytes.

---

## 3. Robustness and Input Validation Analysis

The client enforces strict input validations:
1. **Date-Time Syntax Parsing**:
   - `scheduleMeeting` performs ISO-8601 validation:
     ```kotlin
     val timeStr = meetingMetadata.time
     val normalizedTime = if (timeStr.endsWith("Z")) {
         timeStr.substring(0, timeStr.length - 1) + "+00:00"
     } else {
         timeStr
     }
     try {
         DateTimeFormatter.ISO_DATE_TIME.parse(normalizedTime)
     } catch (e: Exception) {
         throw IllegalArgumentException("Invalid date format: $timeStr", e)
     }
     ```
     This prevents corrupt or malformed dates from being encrypted and sent, causing parsing errors on receiver clients.
2. **Empty File Upload Prevention**:
   - `shareFile` explicitly rejects empty file payloads:
     ```kotlin
     require(fileBytes.isNotEmpty()) { "Cannot upload empty file" }
     ```
     This prevents unnecessary network overhead and zero-byte database entries.
3. **Required Field Verification**:
   - `scheduleMeeting` validates all fields of `MeetingMetadata` before processing:
     ```kotlin
     require(meetingMetadata.title.isNotBlank()) { "Missing required field: title" }
     require(meetingMetadata.time.isNotBlank()) { "Missing required field: time" }
     require(meetingMetadata.location.isNotBlank()) { "Missing required field: location" }
     ```
4. **Missing Decryption Parameters**:
   - `downloadAndDecryptFile` ensures a peer ID is supplied if decrypting a direct message file:
     ```kotlin
     val resolvedPeerId = peerId ?: throw IllegalArgumentException("Missing peerId for DM file decryption")
     ```

---

## 4. Test Suite Coverage Analysis

The client tests in `MessageManagerTest.kt` verify these properties:
- **`testUnitSchedulingMeetings()`**:
  - Verifies scheduling a meeting in a DM channel, checking if the decrypted output matches input metadata, and tests invalid date-time input rejection.
- **`testUnitFileSharing()`**:
  - Verifies the full file upload, metadata transmission, file download, and decryption lifecycle in a DM channel.
- **`testIntegrationAllFlows()`**:
  - Simulates a real client workflow against the active backend (port 8089) for registration, space management, DMs, space messages, scheduling space meetings, sharing space files, and leaving spaces.

All 60 Python E2E tests in the test suite have been successfully executed and pass, verifying feature completeness, boundary/corner cases (such as duplicate usernames, invalid dates, unauthorized space scheduling, empty files, and eavesdropping prevention), and cross-feature workflows.
