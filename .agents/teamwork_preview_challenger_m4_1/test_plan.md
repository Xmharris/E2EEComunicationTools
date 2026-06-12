# Adversarial Cryptographic E2E Test Plan (Tier 5)

This document outlines the design and step-by-step procedures for 5 new adversarial End-to-End (E2E) tests targeting the cryptographic boundaries, exception safety, and trust models of the Secure Space application.

---

## Test 1: Tampered Ciphertext & Tag Integrity Check (Crash Prevention)

### 1. Objective
Verify that if ciphertext or the GCM authentication tag is tampered with in transit, the decryption engine fails cleanly (raises a caught cryptographic exception) and does not crash the client execution flow.

### 2. Steps
1. Register user `alice` and user `bob`.
2. `alice` sends a DM to `bob` containing the plaintext `"Confidential Message"`.
3. Intercept the encrypted hex payload from the database/backend (representing the transit layer).
4. Corrupt the payload:
   - **Scenario A**: Flip a single bit in the ciphertext portion (bytes after the first 12 bytes).
   - **Scenario B**: Flip a single bit in the authentication tag (the last 16 bytes).
5. Inject the tampered hex payload back into `bob`'s incoming message queue.
6. Attempt to decrypt the message using `bob`'s client simulator.

### 3. Verification Oracle (Pass/Fail Criteria)
* **Pass**: The client simulator catches the failure and throws a specific decryption error (`InvalidTag` in Python / `AEADBadTagException` in Kotlin). The application does not crash.
* **Fail**: The decryption completes without error (returning garbage), or the client crashes due to an unhandled exception.

---

## Test 2: Replay Attack Simulation

### 1. Objective
Demonstrate the replay vulnerability where an older encrypted message is re-injected into the message queue and successfully processed by the client because the payload lacks sequence numbers or timestamps.

### 2. Steps
1. Register user `alice` and user `bob`.
2. `alice` sends a DM to `bob` with the text `"Approve Transaction"`.
3. Read the encrypted payload `EP1` from the server.
4. Simulate an attacker by posting a new message to the `/api/messages/send` endpoint with `sender_id = "alice"`, `recipient_id = "bob"`, and the exact same `encrypted_payload = EP1`.
5. `bob` calls `receive_dms()`.

### 3. Verification Oracle (Pass/Fail Criteria)
* **Pass**: `bob`'s client decrypts the replayed message successfully as `"Approve Transaction"`, exposing the vulnerability to replay attacks.
* **Fail**: The client detects and rejects the duplicate payload (e.g., using sequence numbers or timestamps).

---

## Test 3: IV Misuse - Short, Missing, and Reused IVs

### 1. Objective
Verify that the decryption engine handles invalid, short, or missing IVs gracefully without throwing index out of bounds exceptions, and verify the effect of IV reuse.

### 2. Steps
1. Register user `alice` and user `bob`.
2. Derives the static shared key `K_ab`.
3. Craft adversarial payloads:
   - **Payload A**: A hex string of 10 bytes (shorter than the required 12-byte IV).
   - **Payload B**: A hex string of exactly 12 bytes (IV only, empty ciphertext).
   - **Payload C**: A payload that uses a reused IV with different plaintexts (demonstrating how AES-GCM confidentiality fails).
4. Deliver `Payload A` and `Payload B` to `bob`'s client.
5. Attempt to decrypt both.

### 3. Verification Oracle (Pass/Fail Criteria)
* **Pass**: Decrypting `Payload A` and `Payload B` raises a `ValueError("Ciphertext too short")` or `IllegalArgumentException` cleanly.
* **Fail**: The decryption code crashes the runtime with an `IndexOutOfBoundsException` or parses the short IV as valid.

---

## Test 4: Man-in-the-Middle Key Hijacking (Active Impersonation)

### 1. Objective
Verify the impact of the Trust-On-Every-Use (TOEU) vulnerability. An attacker alters a user's public key in the directory, and the peer client silently accepts it and encrypts secret space keys or DMs under the hijacked public key.

### 2. Steps
1. Register user `alice` and user `bob`.
2. Register an attacker `eve`.
3. `eve` issues a malicious POST request to the backend directory, replacing `bob`'s public key with `eve`'s public key.
4. `alice` creates a new space `secret_space` and adds `bob` to it.
5. `alice`'s client fetches `bob`'s public key (which is now `eve`'s key) and derives the shared key `K_ae`.
6. `alice` encrypts the `space_key` under `K_ae` and uploads it to the backend.
7. `eve` downloads the encrypted space key and attempts to decrypt it using her own private key.

### 3. Verification Oracle (Pass/Fail Criteria)
* **Pass**: `eve` successfully decrypts the `space_key` meant for `bob` (verifying that the directory lacks key pinning and is vulnerable to active MITM).
* **Fail**: `alice`'s client rejects the modified public key or `eve` fails to decrypt the space key.

---

## Test 5: Post-Departure Eavesdropping (Key Rotation Failure)

### 1. Objective
Verify that when a member leaves a space, they can still decrypt future messages sent in that space if they have access to the ciphertexts, because the space key is never rotated.

### 2. Steps
1. Register `alice`, `bob`, and `charlie`.
2. `alice` creates `collab_space` and adds `bob` and `charlie` to it.
3. `bob` joins the space and receives the `space_key`.
4. `bob` leaves the space (deleting `space_key` from his local client's memory).
5. `alice` sends a new space message: `"Confidential Future Talk"`.
6. Simulate `bob` obtaining the ciphertext of this message from the backend database (or intercepting it on the wire).
7. `bob` attempts to decrypt the message using the copy of the `space_key` he saved before leaving.

### 3. Verification Oracle (Pass/Fail Criteria)
* **Pass**: `bob` successfully decrypts the message, showing that the system fails to provide Post-Compromise / Backward Security when members leave.
* **Fail**: The message decryption fails because the space key was rotated upon Bob's departure.
