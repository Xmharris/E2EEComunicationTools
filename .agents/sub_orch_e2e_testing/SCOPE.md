# Scope: E2E Test Suite for Secure Space Application

## Architecture
The E2E test suite acts as an independent opaque-box verifier. It runs against a local FastAPI backend (real or simulated) and simulates multiple client instances (simulated Android client nodes) communicating via the backend over HTTP.
All encryption/decryption and key derivation happens inside the client simulation (client-side), ensuring the backend only relays ciphertext.

### Components
1. **Client Simulation**: A Python client class (`ClientSim`) representing a user. It implements:
   - Cryptographic operations: ECDH (X25519) key pairs, shared key derivation, AES-GCM (256-bit) encryption and decryption.
   - API calls: JSON requests to registration, spaces, messages, and file endpoints.
   - Client-side storage: Local tracking of keys, spaces, meetings, and messages.
2. **Mock Backend Server**: A FastAPI application (`mock_backend.py`) that implements the required endpoints for registration, space management, message relay, and file upload/download, using an in-memory or SQLite database.
3. **Test Suite**: A `unittest` or `pytest` collection of E2E tests grouped by Tiers.
4. **Test Runner**: A script (`run_tests.py`) that spins up the mock backend, runs the tests, and cleans up.

---

## Milestones

| # | Name | Scope | Dependencies | Status |
|---|---|---|---|---|
| 1 | Test Infra & Client Sim | Set up the simulated client, mock backend, and test runner in `secure_space_app/tests/` | None | DONE |
| 2 | Tier 1 Feature Tests | Write >= 25 happy path tests covering F1-F5 | M1 | DONE |
| 3 | Tier 2 Boundary Tests | Write >= 25 boundary/edge case/error handling tests covering F1-F5 | M2 | DONE |
| 4 | Tier 3 & Tier 4 Tests | Write >= 5 Tier 3 cross-feature tests and >= 5 Tier 4 real-world scenario tests | M3 | DONE |
| 5 | Verification & TEST_READY | Execute the complete test suite (>= 60 tests), verify layout, write `TEST_READY.md` | M4 | DONE |

---

## Interface Contracts

### 1. User Registration
`POST /api/users/register`
- Request: `{ "username": "alice", "public_key_pem": "<PEM-encoded ECDH Public Key>" }`
- Response: `{ "status": "success", "user_id": 1 }`

### 2. User Directory
`GET /api/users`
- Response: `[{ "id": 1, "username": "alice", "public_key_pem": "..." }, ...]`

### 3. Space Management
`POST /api/spaces/create`
- Request: `{ "name": "Project Alpha", "creator_id": 1 }`
- Response: `{ "space_id": 101 }`

`POST /api/spaces/add_member`
- Request: `{ "space_id": 101, "user_id": 2, "encrypted_space_key": "<Space key encrypted under user 2's public key>" }`
- Response: `{ "status": "success" }`

`GET /api/spaces/{space_id}/key?user_id={user_id}`
- Response: `{ "encrypted_space_key": "..." }`

### 4. Messaging & Relay
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

### 5. File Relay
`POST /api/files/upload`
- Request: Multipart form with encrypted file bytes.
- Response: `{ "file_url": "/api/files/download/{file_id}", "file_id": "uuid-..." }`

`GET /api/files/download/{file_id}`
- Response: Binary stream of encrypted file bytes.
