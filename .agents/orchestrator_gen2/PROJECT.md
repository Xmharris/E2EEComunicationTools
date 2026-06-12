# Project: Secure Space App

## Architecture
The application consists of a local Python backend (FastAPI) and an Android application (Kotlin/Java) communicating over HTTP/JSON.
Encryption is end-to-end: keys are generated and held only by clients. Text, meetings, and shared files are encrypted client-side using AES-GCM (with keys exchanged via ECDH) before transmitting over the network.

### Data Flow
1. **User Registration**: Client generates an ECDH key pair, registers their username and public key with the backend.
2. **Direct Messages (1-on-1)**:
   - Sender retrieves recipient's public key from the backend.
   - Sender performs ECDH key agreement to derive a shared symmetric key.
   - Sender encrypts message payload using AES-GCM and the derived key.
   - Sender uploads ciphertext to the backend.
   - Recipient downloads ciphertext, performs ECDH with sender's public key to derive the same key, and decrypts.
3. **Space/Group Messages**:
   - Creator creates a Space and generates a random symmetric Space Key (AES-256).
   - Creator encrypts the Space Key for themselves and registers the Space.
   - When a new member joins, the Space Key is encrypted using ECDH with the new member's public key and uploaded to the backend (`SpaceKeyExchange`).
   - Members download the encrypted Space Key, decrypt it using their private key, and use it to encrypt/decrypt all space messages, meetings, and file metadata.
4. **Meeting Scheduling**:
   - Creator serializes meeting metadata (title, description, date, time) to JSON.
   - Creator encrypts JSON with the Space Key (or DM shared key) and sends it as a special message payload.
5. **Content Sharing (File attachments)**:
   - Client generates a random file encryption key (AES-256).
   - Client encrypts the file data and uploads ciphertext to the backend.
   - Client serializes file metadata (name, size, mime type, hash, backend download URL) and the file key (encrypted with the Space/DM key) and uploads it as a message payload.
   - Recipient receives the message, decrypts the file key, downloads the ciphertext from the backend, and decrypts the file.

## Code Layout
- `secure_space_app/backend/` - FastAPI backend application, SQLite database, file store.
- `secure_space_app/client/` - Android App Gradle project.
  - `app/src/main/java/com/secure/space/crypto/` - Cryptographic Engine.
  - `app/src/main/java/com/secure/space/api/` - Network Client.
  - `app/src/main/java/com/secure/space/model/` - Models (User, Message, Space, Meeting).
  - `app/src/main/java/com/secure/space/db/` - Room database cache.
- `secure_space_app/tests/` - E2E test suite.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| 0 | E2E Testing Track | Comprehensive E2E test harness and cases (Tiers 1-4) | None | DONE |
| 1 | Cryptographic Core & Backend | FastAPI backend API, local SQLite, core client ECDH/AES crypto library | None | DONE |
| 2 | Spaces & DM Communication | Android client user registry, space management, private messaging | M1 | PLANNED |
| 3 | Meetings & Content Sharing | Meeting scheduling payloads, file upload/download client-side encryption | M2 | PLANNED |
| 4 | Verification & Hardening | Full integration testing, Challenger white-box test generation, Forensic Audit | M0, M3 | PLANNED |

## Interface Contracts
### Client ↔ Backend REST API

#### 1. User Registration
`POST /api/users/register`
- Request: `{ "username": "alice", "public_key_pem": "<PEM-encoded ECDH Public Key>" }`
- Response: `{ "status": "success", "user_id": 1 }`

#### 2. User Directory
`GET /api/users`
- Response: `[{ "id": 1, "username": "alice", "public_key_pem": "..." }, ...]`

#### 3. Space Management
`POST /api/spaces/create`
- Request: `{ "name": "Project Alpha", "creator_id": 1 }`
- Response: `{ "space_id": 101 }`

`POST /api/spaces/add_member`
- Request: `{ "space_id": 101, "user_id": 2, "encrypted_space_key": "<Space key encrypted under user 2's public key>" }`
- Response: `{ "status": "success" }`

`GET /api/spaces/{space_id}/key?user_id={user_id}`
- Response: `{ "encrypted_space_key": "..." }`

#### 4. Messaging & Relay
`POST /api/messages/send`
- Request:
  ```json
  {
    "sender_id": 1,
    "recipient_id": null,
    "space_id": 101,
    "payload_type": "text | meeting | file",
    "encrypted_payload": "<AES-GCM ciphertext>",
    "iv": "<Initialization Vector>",
    "sender_public_key_pem": "<for DM key derivation verification>"
  }
  ```
- Response: `{ "status": "success", "message_id": 501 }`

`GET /api/messages?user_id={user_id}&space_id={space_id}`
- Response: List of messages matching criteria.

#### 5. File Relay
`POST /api/files/upload`
- Request: Multipart form with encrypted file bytes.
- Response: `{ "file_url": "/api/files/download/{file_id}", "file_id": "uuid-..." }`

`GET /api/files/download/{file_id}`
- Response: Binary stream of encrypted file bytes.
