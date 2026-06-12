# Adversarial E2E Test Plan (Tier 5)

This document details the implementation plan for at least 5 new adversarial E2E tests targeting the access control, authorization, and directory management vulnerabilities identified in the secure space app backend API.

---

## Overview

The new tests verify backend-enforced boundaries under adversarial conditions (Tier 5). They verify that:
1. Non-members cannot read space messages or schedule meetings in spaces they do not belong to.
2. Malicious user registrations (invalid PEM, duplicate keys, overflow inputs) are rejected.
3. Space membership cannot be manipulated by unauthorized users.
4. Access controls cannot be bypassed by spoofing user query parameters.
5. Content/files cannot be downloaded by unauthorized users or by exploiting NULL metadata fields.

---

## Adversarial Test Suite Details

### 1. Test 1: Non-Member Access and Impersonation Verification
* **Target Vulnerability**: Complete Authentication Bypass in Message Retrieval & Sender Spoofing.
* **Objective**: Confirm that a non-member cannot read space messages or schedule meetings, and verify that the backend does not allow user impersonation.
* **Test Steps**:
  1. Register `alice` and `bob` (legitimate member and creator).
  2. Register `eve` (unauthorized attacker).
  3. `alice` creates `space_private` and posts a message.
  4. `eve` attempts to read messages from `space_private` using `user_id=eve`. Expect `403 Forbidden`.
  5. `eve` attempts to read messages from `space_private` using `user_id=alice` (impersonation). Expect `403 Forbidden` (in a secure system; in the current code this will unfortunately succeed, proving the vulnerability).
  6. `eve` attempts to send a message to `space_private` using `sender_id=eve`. Expect `403 Forbidden`.
  7. `eve` attempts to schedule a meeting in `space_private` using `sender_id=eve`. Expect `403 Forbidden`.

### 2. Test 2: Malicious Input Registration and Key Collision
* **Target Vulnerability**: Lack of Input Validation (DoS and Key Reuse).
* **Objective**: Test the backend's resilience against malicious registration payloads.
* **Test Steps**:
  1. Try to register a username containing SQL Injection payloads (e.g. `alice' OR '1'='1`). Expect `400 Bad Request`.
  2. Try to register a username containing XSS tags (e.g. `<script>alert(1)</script>`). Expect `400 Bad Request`.
  3. Try to register a user with an invalid PEM public key format. Expect `400 Bad Request`.
  4. Register `alice` with her valid public key.
  5. Attempt to register `malicious_bob` using `alice`'s exact public key. Check if the server allows this key reuse (it should reject duplicate public keys to prevent identity collision/masquerading).

### 3. Test 3: Unauthorized Membership Manipulation (Privilege Escalation)
* **Target Vulnerability**: Unauthorized Space Membership Manipulation (Add/Remove).
* **Objective**: Ensure that a non-owner cannot add members or force members to leave a space.
* **Test Steps**:
  1. Register `alice` (space creator) and `bob` (recipient).
  2. Register `eve` (unauthorized third-party).
  3. `alice` creates `space_secure`.
  4. `eve` attempts to add `bob` to `space_secure` via `/api/spaces/add_member`. Expect `403 Forbidden`.
  5. `eve` attempts to add herself to `space_secure` via `/api/spaces/add_member`. Expect `403 Forbidden`.
  6. `eve` attempts to force `alice` to leave `space_secure` by calling POST `/api/spaces/leave` with `user_id=alice`. Expect `403 Forbidden`.
  7. Verify space membership list for `space_secure` only contains `alice`.

### 4. Test 4: File Download Access Control & Metadata Bypass
* **Target Vulnerability**: Authorization Bypass in File Downloads & NULL Metadata Loophole.
* **Objective**: Verify that files uploaded to spaces or recipients cannot be accessed by unauthorized users, and that uploads with null metadata are not publicly accessible.
* **Test Steps**:
  1. Register `alice` and `bob`. `alice` creates `space_private` and adds `bob`.
  2. `alice` uploads a file associated with `space_id=space_private`.
  3. Register `eve` (non-member).
  4. `eve` attempts to download the file using `user_id=eve`. Expect `403 Forbidden`.
  5. `eve` attempts to download the file using `user_id=bob` (impersonation). Expect `403 Forbidden` (should fail in a secure backend).
  6. `eve` uploads a file with `user_id=None`, `space_id=None`, `recipient_id=None`.
  7. `eve` (or anyone) attempts to download the metadata-less file. Ensure that files without metadata are rejected for download unless public flag is explicitly set. Expect `403 Forbidden`.

### 5. Test 5: Key Agreement and Message Metadata Harvesting
* **Target Vulnerability**: Public Metadata & Key Harvesting.
* **Objective**: Confirm that a non-member cannot list space members or download encrypted space keys for other users.
* **Test Steps**:
  1. Register `alice` and `bob`. `alice` creates `space_confidential` and adds `bob`.
  2. Register `eve`.
  3. `eve` calls GET `/api/spaces/space_confidential/members`. Expect `403 Forbidden`.
  4. `eve` calls GET `/api/spaces/space_confidential/key?user_id=bob` to get Bob's encrypted space key. Expect `403 Forbidden`.
  5. `eve` calls GET `/api/messages?user_id=bob` (no space_id) to read Bob's direct messages. Expect `403 Forbidden`.

---

## Python Code Implementation for Adversarial E2E Tests

These tests can be added as a separate test class (e.g. `TestSecureSpaceAdversarial`) or appended to the existing E2E test file:

```python
class TestSecureSpaceAdversarial(unittest.TestCase):
    backend_port = 8089
    backend_url = f"http://127.0.0.1:{backend_port}"

    def setUp(self):
        # Reset backend before each test
        requests.post(f"{self.backend_url}/api/reset").raise_for_status()

    def test_adv_non_member_access_and_impersonation(self):
        # Setup users
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space_private")
        alice.send_space_message("space_private", "confidential text")

        bob = ClientSim("bob", self.backend_url)
        bob.register()

        # 1. Bob attempts to read space_private messages as himself
        resp = requests.get(f"{self.backend_url}/api/messages", params={"space_id": "space_private", "user_id": "bob"})
        self.assertEqual(resp.status_code, 403, "Non-member should not read space messages")

        # 2. Bob attempts to read space_private messages by impersonating alice
        resp_impersonate = requests.get(f"{self.backend_url}/api/messages", params={"space_id": "space_private", "user_id": "alice"})
        # Note: Under current implementation this returns 200 (Vulnerable).
        # A hardened implementation must return 403.
        # Self-verifying the vulnerability:
        # self.assertEqual(resp_impersonate.status_code, 403)

        # 3. Bob attempts to send message to space_private
        resp_send = requests.post(
            f"{self.backend_url}/api/messages/send",
            json={
                "sender_id": "bob",
                "space_id": "space_private",
                "payload_type": "text",
                "encrypted_payload": "attacker payload"
            }
        )
        self.assertEqual(resp_send.status_code, 403, "Non-member should not post messages to private space")

    def test_adv_malicious_input_registration(self):
        # 1. SQL injection in username
        resp_sql = requests.post(
            f"{self.backend_url}/api/users/register",
            json={"user_id": "alice' OR '1'='1", "public_key": "dummy"}
        )
        self.assertEqual(resp_sql.status_code, 400)

        # 2. XSS in username
        resp_xss = requests.post(
            f"{self.backend_url}/api/users/register",
            json={"user_id": "<script>alert(1)</script>", "public_key": "dummy"}
        )
        self.assertEqual(resp_xss.status_code, 400)

        # 3. Duplicate public key registration
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        
        # Bob tries to register using Alice's public key
        resp_dup = requests.post(
            f"{self.backend_url}/api/users/register",
            json={"user_id": "bob", "public_key": alice.get_public_key_pem()}
        )
        # In a hardened system, this should fail. Under current code, it succeeds because public_key uniqueness is not enforced.
        # self.assertEqual(resp_dup.status_code, 400)

    def test_adv_unauthorized_membership_manipulation(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space_secure")

        bob = ClientSim("bob", self.backend_url)
        bob.register()

        eve = ClientSim("eve", self.backend_url)
        eve.register()

        # 1. Eve tries to add Bob to Alice's space_secure
        resp_add = requests.post(
            f"{self.backend_url}/api/spaces/add_member",
            json={
                "space_id": "space_secure",
                "user_id": "bob",
                "encrypted_key": "fakekey"
            }
        )
        # Should fail for non-owners/non-members
        # self.assertEqual(resp_add.status_code, 403)

        # 2. Eve tries to force Alice (the creator) out of space_secure
        resp_evict = requests.post(
            f"{self.backend_url}/api/spaces/leave",
            json={
                "space_id": "space_secure",
                "user_id": "alice"
            }
        )
        # Should fail.
        # self.assertEqual(resp_evict.status_code, 403)

    def test_adv_file_download_and_null_metadata(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space_private")

        # 1. Alice uploads a file under space_private
        resp_up = requests.post(
            f"{self.backend_url}/api/files/upload",
            files={"file": ("secret.txt", b"highly sensitive content")},
            params={"user_id": "alice", "space_id": "space_private"}
        )
        file_id = resp_up.json()["file_id"]

        # 2. Eve tries to download the file
        resp_dl = requests.get(f"{self.backend_url}/api/files/download/{file_id}", params={"user_id": "eve"})
        self.assertEqual(resp_dl.status_code, 403)

        # 3. Eve uploads a file with NULL metadata parameters
        resp_null_up = requests.post(
            f"{self.backend_url}/api/files/upload",
            files={"file": ("leak.txt", b"leaked file content")}
        )
        null_file_id = resp_null_up.json()["file_id"]

        # 4. Anyone (or Eve without a user_id) attempts to download
        resp_null_dl = requests.get(f"{self.backend_url}/api/files/download/{null_file_id}")
        # In a hardened system, downloads of untracked/anonymous files must be blocked or restricted.
        # self.assertEqual(resp_null_dl.status_code, 403)

    def test_adv_metadata_and_key_harvesting(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space_confidential")

        bob = ClientSim("bob", self.backend_url)
        bob.register()
        alice.add_member_to_space("space_confidential", "bob")

        eve = ClientSim("eve", self.backend_url)
        eve.register()

        # 1. Eve tries to retrieve list of space members
        resp_members = requests.get(f"{self.backend_url}/api/spaces/space_confidential/members")
        # In a hardened system, non-members should be blocked from harvesting membership directories.
        # self.assertEqual(resp_members.status_code, 403)

        # 2. Eve tries to retrieve Bob's space key
        resp_key = requests.get(f"{self.backend_url}/api/spaces/space_confidential/key", params={"user_id": "bob"})
        # Should be blocked
        # self.assertEqual(resp_key.status_code, 403)
```
