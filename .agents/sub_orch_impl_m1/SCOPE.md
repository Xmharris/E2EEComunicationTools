# Scope: Cryptographic Core & Backend (Milestone 1)

## Architecture
This milestone implements:
1. **Local FastAPI Backend**: A Python backend running on a standard port (e.g. 8000) using SQLite for database persistence. The backend acts as a relay for encrypted payloads (DMs, space messages, keys, files) and handles user/space directories.
2. **Client Cryptographic Core**: A Kotlin/Java library/classes implementing ECDH (secp256r1 or Curve25519) key exchange, AES-GCM (256-bit) encryption/decryption, and HKDF key derivation.
3. **API Integration & Core Verification**: Verification tests demonstrating endpoint compliance and cryptographic correctness.

### Data Flow & Interfaces
- **User Registration**:
  `POST /api/users/register`
  Request: `{ "username": "alice", "public_key_pem": "<PEM-encoded ECDH Public Key>" }`
  Response: `{ "status": "success", "user_id": 1 }`
  
- **User Directory**:
  `GET /api/users`
  Response: `[{ "id": 1, "username": "alice", "public_key_pem": "..." }, ...]`

- **Space/Group Key Exchanges**:
  `POST /api/spaces/create`
  Request: `{ "name": "Space Name", "creator_id": 1 }`
  Response: `{ "space_id": 101 }`

  `POST /api/spaces/add_member`
  Request: `{ "space_id": 101, "user_id": 2, "encrypted_space_key": "<Space key encrypted under user 2's public key>" }`
  Response: `{ "status": "success" }`

  `GET /api/spaces/{space_id}/key?user_id={user_id}`
  Response: `{ "encrypted_space_key": "..." }`

- **Message Posting & Retrieval**:
  `POST /api/messages/send`
  Request:
  ```json
  {
    "sender_id": 1,
    "recipient_id": null,
    "space_id": 101,
    "payload_type": "text",
    "encrypted_payload": "<AES-GCM ciphertext>",
    "iv": "<Initialization Vector>",
    "sender_public_key_pem": "<PEM-encoded public key>"
  }
  ```
  Response: `{ "status": "success", "message_id": 501 }`

  `GET /api/messages?user_id={user_id}&space_id={space_id}` (if space_id is null, gets DMs for user_id)
  Response: List of message objects.

- **File upload and download**:
  `POST /api/files/upload`
  Multipart form with encrypted file bytes.
  Response: `{ "file_url": "/api/files/download/{file_id}", "file_id": "uuid-..." }`

  `GET /api/files/download/{file_id}`
  Returns binary stream of file bytes.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | SQLite Database & FastAPI Skeleton | Setup FastAPI project structure, database models/migrations, and SQLite configuration | None | PLANNED |
| 2 | Backend API Endpoints | Implement all routes (Users, Spaces, Messages, Files) with SQLite persistence | M1.1 | PLANNED |
| 3 | Client Cryptographic Core | Implement Kotlin/Java cryptographic primitives: ECDH, HKDF, AES-GCM (256-bit), and serialization | None | PLANNED |
| 4 | Verification & Unit Tests | Implement Python FastAPI tests and Kotlin JUnit tests to verify correctness and integration | M1.2, M1.3 | PLANNED |
| 5 | Integrity Audit & Handoff | Run Forensic Auditor checklist, compile test logs, write handoff, and report to parent | M1.4 | PLANNED |

## Interface Contracts
### Primitives
- **ECDH**: Curve25519 (X25519) or secp256r1. We will use Curve25519 (X25519) if supported, or secp256r1. Since Curve25519 is very standard and widely supported in modern Java (JDK 11+ has X25519, or BouncyCastle can be used), let's use secp256r1 or X25519. We will have the Explorer investigate what standard libraries are available on Android and Python.
- **AES-GCM**: AES/GCM/NoPadding, 256-bit key size, 12-byte (96-bit) IV, 16-byte (128-bit) tag size.
- **HKDF**: HKDF-SHA256.
- **Key serialization**: PEM or Base64 representation.
