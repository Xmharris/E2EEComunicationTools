# E2E Test Suite Readiness Report — Secure Space E2EE Application

This document provides instructions on how to run the E2E test suite for the Secure Space End-to-End Encrypted (E2EE) Application and details the test coverage.

## How to Run the Test Suite

### 1. Prerequisites
Ensure you have Python 3.9+ installed along with the required packages. You can install all dependencies via `pip`:
```bash
pip install fastapi uvicorn requests cryptography pydantic
```

### 2. Execution Command
From the project root directory (`C:\Users\xavie\Documents\antigravity\quick-franklin`), run the test runner script:
```bash
python secure_space_app/tests/run_tests.py
```

This script will automatically:
1. Start the FastAPI mock backend server on a background daemon thread (listening on `http://127.0.0.1:8089`).
2. Run all 60 E2E tests using `unittest`.
3. Properly tear down the mock backend server and clean up.
4. Exit with code `0` if all tests pass, and non-zero if any test fails.

---

## Test Suite Coverage Matrix

The E2E test suite consists of **60 distinct tests** organized into a four-tier structure covering 5 core E2EE features:

### Core Features Under Test
- **Feature 1**: User Registration & Public Key Registry
- **Feature 2**: Space/Channel Management
- **Feature 3**: Direct Messaging (1-on-1 private messaging)
- **Feature 4**: Meeting Scheduling
- **Feature 5**: Content Sharing (file upload/download with client-side encryption)

---

### Tier 1: Feature Coverage (25 Tests)

#### Feature 1: User Registration & Public Key Registry
1. `test_registration_success`: Registers a single user successfully and verifies the response.
2. `test_registration_retrieves_pem`: Confirms the public key PEM stored on the backend matches the client's generated key.
3. `test_multiple_users_registration`: Verifies that multiple users can register and retrieve their respective public keys.
4. `test_registration_response_structure`: Asserts the API response JSON structure is correct (`status`, `user_id`).
5. `test_user_directory_contains_all`: Verifies the user directory contains all registered user IDs.

#### Feature 2: Space/Channel Management
6. `test_space_creation`: Confirms spaces can be created successfully by a registered user.
7. `test_add_member_to_space`: Verifies the creator can add another user to the space.
8. `test_retrieve_space_key`: Verifies that added members can retrieve and decrypt the space key.
9. `test_space_member_list`: Ensures the list of space members is returned correctly.
10. `test_multiple_spaces_creation`: Confirms correct key isolation across multiple spaces.

#### Feature 3: Direct Messaging
11. `test_send_dm`: Validates successful transmission of direct messages between two users.
12. `test_receive_dm`: Verifies direct messages are received.
13. `test_dm_decryption`: Verifies that the recipient can successfully decrypt the DM using their derived key.
14. `test_dm_recipient_filtering`: Verifies that a third party cannot retrieve or see DMs intended for others.
15. `test_bidirectional_dm`: Validates bidirectional direct message flow and correct decryption by both parties.

#### Feature 4: Meeting Scheduling
16. `test_schedule_meeting_in_space`: Verifies scheduling a meeting in a space sends the correct encrypted payload.
17. `test_receive_space_meeting`: Verifies space members receive meeting notifications.
18. `test_decrypt_space_meeting`: Confirms space members can decrypt and parse meeting metadata (title, time, location).
19. `test_schedule_meeting_in_dm`: Validates scheduling a meeting via DM.
20. `test_decrypt_dm_meeting`: Verifies the recipient can decrypt and parse the DM meeting metadata.

#### Feature 5: Content Sharing
21. `test_upload_file`: Verifies successful upload of client-side encrypted file bytes.
22. `test_download_file`: Validates downloading and decrypting files successfully.
23. `test_share_file_in_space`: Verifies that file metadata can be shared with a space.
24. `test_share_file_in_dm`: Verifies sharing file metadata in a DM.
25. `test_decrypt_shared_file`: Confirms recipients can decrypt the file metadata and download/decrypt the file.

---

### Tier 2: Boundary & Corner Cases (25 Tests)

#### Feature 1: User Registration
26. `test_register_duplicate_username`: Confirms backend rejects duplicate registration with `400 Bad Request`.
27. `test_register_invalid_pem_key`: Verifies backend rejects invalid PEM format with `400 Bad Request`.
28. `test_register_empty_username`: Verifies backend rejects empty/whitespace usernames.
29. `test_register_extremely_long_username`: Validates rejection of usernames > 100 characters.
30. `test_register_special_chars_username`: Ensures usernames are restricted to alphanumeric, dashes, and underscores.

#### Feature 2: Space/Channel Management
31. `test_non_member_retrieve_space_key`: Verifies non-members receive `404 Not Found` when trying to fetch a space key.
32. `test_add_non_existent_user_to_space`: Ensures adding an unregistered user to a space fails with `404 Not Found`.
33. `test_add_member_duplicate`: Validates that adding an already existing member fails with `400 Bad Request`.
34. `test_create_space_empty_name`: Confirms space creation fails for empty/whitespace names.
35. `test_retrieve_key_non_existent_space`: Verifies retrieving the key for a non-existent space returns `404 Not Found`.

#### Feature 3: Direct Messaging
36. `test_send_dm_to_self`: Confirms users cannot send direct messages to themselves.
37. `test_send_dm_to_non_existent_user`: Confirms sending a DM to an unregistered recipient returns `404 Not Found`.
38. `test_send_empty_payload_dm`: Verifies empty encrypted payloads are rejected.
39. `test_dm_decrypt_with_wrong_key`: Asserts that trying to decrypt a DM using a different user's key raises an exception.
40. `test_send_dm_with_invalid_iv`: Confirms decryption fails when the IV is too short or invalid.

#### Feature 4: Meeting Scheduling
41. `test_meeting_invalid_date_format`: Verifies client-side date format validation rejects non-ISO formats.
42. `test_meeting_missing_required_fields`: Confirms meeting scheduling fails if title, time, or location is missing.
43. `test_meeting_unauthorized_space_schedule`: Verifies that a non-member scheduling a meeting in a space is rejected with `403 Forbidden`.
44. `test_decrypt_meeting_with_wrong_space_key`: Asserts decryption fails when using a wrong space key.
45. `test_meeting_extremely_long_description`: Verifies large meeting payloads (50KB description) are transmitted and parsed correctly.

#### Feature 5: Content Sharing
46. `test_download_non_existent_file`: Confirms downloading a non-existent file returns `404 Not Found`.
47. `test_upload_empty_file`: Ensures uploading an empty (0 bytes) file returns `400 Bad Request`.
48. `test_decrypt_file_wrong_key`: Verifies file decryption fails when using the wrong key.
49. `test_share_file_non_member`: Confirms non-members are blocked from sharing files in a space (`403 Forbidden`).
50. `test_upload_large_file`: Verifies successful upload, download, and decryption of a 1MB file.

---

### Tier 3: Cross-Feature Combinations (5 Tests)
51. `test_space_meeting_with_file_attachment`: Schedules a meeting inside a space referencing an encrypted file attachment; space members download and decrypt the attachment.
52. `test_dm_meeting_with_file_attachment`: Schedules a 1-on-1 meeting referencing an encrypted file attachment; recipient downloads and decrypts the attachment.
53. `test_file_sharing_referencing_other_space_file`: Alice shares a file in Space A; Bob downloads it, re-encrypts it, and shares it in Space B; Charlie (only in Space B) downloads and decrypts it successfully.
54. `test_user_leaves_space_and_receives_dms`: Bob leaves a space, is immediately blocked from accessing space messages, but successfully receives and decrypts direct messages from Alice.
55. `test_send_file_and_message_in_space_atomic_flow`: Alice embeds file metadata directly inside a space text message payload; Bob parses the text, extracts metadata, and decrypts the file.

---

### Tier 4: Real-World Application Scenarios (5 Tests)
56. `test_multi_user_onboarding_and_secure_setup`: Simulates 5 users onboarding, establishing public keys, creating multiple distinct spaces, distributing keys, and joining.
57. `test_wire_level_encryption_verification`: Directly inspects the mock backend database to verify that all message payloads are fully encrypted (i.e. zero plaintext leaks).
58. `test_key_agreement_verification`: Verifies the mathematical properties of the ECDH key exchange (symmetry between Alice/Bob, uniqueness against Charlie).
59. `test_secure_collaborative_workflow`: Simulates a full collaborative cycle (meeting setup, document draft upload, peer download/edit/upload, creator verification of final version).
60. `test_unauthorized_eavesdropping_prevention`: Simulates an adversary (Eve) attempting to fetch keys, read database messages, or download files from spaces she doesn't belong to, verifying she is blocked from accessing plaintext.
