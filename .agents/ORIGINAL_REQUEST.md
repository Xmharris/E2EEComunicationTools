# Original User Request

## Initial Request — 2026-06-11T21:37:47Z

An Android application and local backend that allows multiple users to communicate, schedule meetings, and share content securely using end-to-end encryption (E2EE).

Working directory: C:\Users\xavie\Documents\antigravity\quick-franklin\secure_space_app
Integrity mode: benchmark

## Requirements

### R1. Secure Communication Spaces
- Users can create or join shared "spaces" (channels) as well as communicate in direct 1-on-1 private messaging.
- Messages, meeting invitations, and shared content must be end-to-end encrypted before transmission.

### R2. End-to-End Encryption (E2EE)
- All cryptographic key generation and message encryption/decryption must happen entirely client-side.
- The server/backend must only act as a relay for encrypted payloads and must not have access to private keys or plaintext message content.

### R3. Meeting Scheduling
- Users can schedule meetings (date, time, title, description) within a space.
- Meeting invitations/details are shared securely and E2EE-encrypted.

### R4. Content Sharing
- Users can share content (text, links, files/attachments) within the space.
- Content must be encrypted client-side before upload/sharing.

### R5. Local Backend
- A simple local backend (e.g. Node.js or Python) that acts as a coordinator, user directory, and relay server for encrypted payloads.

## Acceptance Criteria

### E2EE & Cryptographic Integrity
- [ ] Programmatic verification tests must run and pass, proving that message payloads intercepted on the wire (or recorded by the backend) are encrypted (cannot be read as plaintext).
- [ ] Verification tests must demonstrate that the backend does not receive or store private keys, and cannot decrypt the messages.
- [ ] Verification tests must show that two clients can successfully exchange keys, encrypt messages, transmit them via the backend, and decrypt them to recover the original plaintext.

### Communication Features
- [ ] A test script or suite verifies successful creation of spaces, sending/receiving of direct messages, and group/channel messages.
- [ ] The app compiles and can be launched or simulated (using standard unit/integration test frameworks like JUnit, Robolectric, or similar) to verify core logic.

### Meeting & Sharing Features
- [ ] Automated tests verify that meeting creation payloads are encrypted and correctly parsed by the recipient client.
- [ ] Automated tests verify that shared content payloads are encrypted on upload/send and decrypted on download/receive.
