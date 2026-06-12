# Scope: Milestone 3 - Verification of Meeting Scheduling and Content Sharing

## Architecture
- **Client Application**: Secure Space Android Client (Kotlin)
  - `MessageManager.kt`: Handles client-side crypto, meeting scheduling, and file sharing/downloading.
  - `MessageManagerTest.kt`: Unit and integration testing of the cryptographic flows, meeting scheduling, and file sharing.
- **Backend API**: Secure Space Server (Python)
  - The backend stores encrypted messages, meeting payloads, and files, but MUST NOT store private keys. Wire transmission must be encrypted using AES-GCM and ECDH.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| 1 | Code Inspection | Inspect existing `MessageManager.kt` and `MessageManagerTest.kt` implementations | None | DONE |
| 2 | Code Verification & Run | Run Kotlin unit tests and Python E2E integration test suite via Worker | 1 | DONE |
| 3 | Input Validation & Cryptographic Auditing | Ensure robust handling of invalid inputs and client-side end-to-end encryption | 2 | DONE |
| 4 | Forensic Integrity Audit | Run Forensic Auditor to confirm clean execution and zero integrity violations | 3 | DONE |

## Interface Contracts
### `MessageManager` API
- `scheduleMeeting(title: String, description: String, date: String, time: String, participants: List<String>): String`
  - Encrypts meeting details (title, description, date, time) with a symmetric key derived via ECDH.
- `decryptMeeting(encryptedPayload: String, senderPublicKey: String): MeetingDetails`
  - Decrypts meeting payload using the sender's public key and recipient's private key.
- `shareFile(filePath: String, recipientPublicKeys: Map<String, String>): SharedFileMetadata`
  - Encrypts file with generated AES-GCM key, encrypts AES key per recipient using ECDH, uploads to server.
- `decryptFileMetadata(encryptedMetadata: String, senderPublicKey: String): DecryptedFileMetadata`
  - Decrypts file metadata (name, size, key).
- `downloadAndDecryptFile(fileId: String, decryptionKey: ByteArray): ByteArray`
  - Downloads encrypted file and decrypts it with the symmetric key.
