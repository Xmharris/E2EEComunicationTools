# Adversarial Gap Report: Secure Space Backend API

## Challenge Summary

**Overall risk assessment**: CRITICAL

The backend implementation (`secure_space_app/backend/app/main.py`) suffers from multiple critical security flaws. Because the API lacks authentication (e.g., token-based, session-based, or signature-based verification) and relies entirely on user-supplied query parameters or request body IDs to enforce access control, any caller can impersonate any registered user. This leads to complete authorization bypasses, privilege escalation, metadata leakage, and denial of service.

---

## Challenges

### [Critical] Challenge 1: Unauthorized Space Membership Manipulation
- **Assumption challenged**: Only space creators/owners or current space members can add or remove members in a space.
- **Attack scenario**:
  - An attacker (Eve) can call POST `/api/spaces/add_member` and add herself (or any other user) to any existing space by providing the space ID and an arbitrary encrypted key.
  - Eve can call POST `/api/spaces/leave` with `user_id="alice"` (where Alice is the space creator) to evict Alice from her own space.
- **Blast radius**: Complete compromise of space memberships. Attackers can force entry into private spaces or perform a Denial of Service (DoS) by evicting legitimate users and owners.
- **Mitigation**: Implement token-based authentication (JWT or session). Validate that the requester of `/api/spaces/add_member` is the space owner/creator, and that the requester of `/api/spaces/leave` is either the user themselves or the space owner.

### [Critical] Challenge 2: Complete Authentication Bypass in Message Retrieval
- **Assumption challenged**: Only the user matching the `user_id` query parameter can retrieve their direct messages or space messages.
- **Attack scenario**:
  - An attacker can call GET `/api/messages?user_id=target_user` to download all direct messages belonging to `target_user`.
  - An attacker can call GET `/api/messages?space_id=space_private&user_id=member_user` to download all messages in `space_private` by providing the username of a valid member (which can be obtained publicly).
- **Blast radius**: Complete loss of confidentiality for all DMs and space messages. Although the payloads are encrypted, the metadata is fully exposed, and the encrypted payloads can be harvested for offline cryptanalysis.
- **Mitigation**: Authenticate requests and verify that the authenticated caller's identity matches the requested `user_id`.

### [High] Challenge 3: Authorization Bypass in File Downloads
- **Assumption challenged**: Only authorized uploaders, space members, or DM recipients can download shared files.
- **Attack scenario**:
  - Since `user_id` is just a query parameter, an attacker can download any file by calling GET `/api/files/download/{file_id}?user_id=authorized_user`.
  - If a file is uploaded without `user_id`, `space_id`, or `recipient_id` parameters (which are optional in `/api/files/upload`), the database stores these fields as `NULL`. When downloading such a file, the backend skips all check blocks and returns the file bytes to any caller without requiring a `user_id`.
- **Blast radius**: Unauthorized access to sensitive uploaded files and data leakage of metadata-less files.
- **Mitigation**: Secure `/api/files/download/{file_id}` by matching the authenticated caller's identity against the file's ownership or space membership. Reject downloads of files without metadata unless public access is explicitly intended.

### [High] Challenge 4: Public Metadata & Key Harvesting
- **Assumption challenged**: Only members of a space can retrieve the list of space members or encrypted space keys.
- **Attack scenario**:
  - Anyone can call GET `/api/spaces/{space_id}/members` to retrieve the complete list of member usernames for any space.
  - Anyone can call GET `/api/spaces/{space_id}/key?user_id={member}` to retrieve the encrypted space key and `creator_id` for any member in the space.
- **Blast radius**: Extensive metadata leakage. Attackers can map out space memberships and harvest encrypted space keys without belonging to the spaces.
- **Mitigation**: Restrict key and member retrieval to authenticated users who are verified members of the specified space.

### [Medium] Challenge 5: Identity Spoofing in Messages and File Uploads
- **Assumption challenged**: The `sender_id` or `user_id` parameter represents the actual sender/uploader.
- **Attack scenario**:
  - An attacker can send a message with `sender_id="alice"` or upload a file with `user_id="alice"`, making it appear in the database as though Alice sent the message or uploaded the file.
- **Blast radius**: Identity spoofing and social engineering.
- **Mitigation**: Derive the sender identity from the authenticated session token rather than user-supplied request payloads.

### [Medium] Challenge 6: Input Validation Gaps (DoS and Key Reuse)
- **Assumption challenged**: Inputs are properly sized, formatted, and validated.
- **Attack scenario**:
  - The `/api/users/register` endpoint has no length limit on the `public_key` field, allowing an attacker to submit multi-megabyte payloads to exhaust server memory during cryptographic parsing (`load_pem_public_key`) or database storage.
  - The `/api/files/upload` endpoint reads the entire file into memory using `file.read()`, which can lead to Out-Of-Memory (OOM) crashes if a large file is uploaded.
  - The system allows multiple users to register with the exact same public key, leading to cryptographic identity collision.
- **Blast radius**: Memory exhaustion, database bloat, server denial of service (DoS), and key collision.
- **Mitigation**: Limit public key length (e.g., max 4KB). Stream file uploads to temporary storage rather than loading them completely in memory, and enforce a maximum file size limit. Validate public key uniqueness.

### [High] Challenge 7: Public Database Reset Endpoint
- **Assumption challenged**: The database reset endpoint is protected or only accessible in local test environments.
- **Attack scenario**:
  - Any client can send a POST to `/api/reset` to immediately delete all database tables.
- **Blast radius**: Complete loss of all application data and total service disruption.
- **Mitigation**: Disable `/api/reset` in production and secure it with administrative credentials or API keys.

---

## Stress Test Results

- **Eve attempts to add herself to Alice's private space** → Expected: `403 Forbidden` / `401 Unauthorized` → Actual: `200 OK` (Added successfully) → **FAIL**
- **Eve attempts to evict Alice from Alice's own space** → Expected: `403 Forbidden` / `401 Unauthorized` → Actual: `200 OK` (Left successfully) → **FAIL**
- **Eve attempts to download Bob's private DMs** → Expected: `403 Forbidden` / `401 Unauthorized` → Actual: `200 OK` (DMs returned) → **FAIL**
- **Eve attempts to download a file from Alice's private space by spoofing Bob's user_id** → Expected: `403 Forbidden` / `401 Unauthorized` → Actual: `200 OK` (File downloaded) → **FAIL**
- **Eve attempts to retrieve a file uploaded with null metadata** → Expected: `403 Forbidden` / `401 Unauthorized` → Actual: `200 OK` (File downloaded) → **FAIL**

---

## Unchallenged Areas

- **Cryptographic Algorithms Strength** — The actual RSA and AES-GCM encryption/decryption operations are performed on the client side (simulated in `ClientSim`). The strength of the cryptographic algorithms themselves was not challenged, as the focus is on the backend REST API access controls.
