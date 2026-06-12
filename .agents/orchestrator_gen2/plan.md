# Project Plan: Secure E2EE Communication App

## Overview
This plan describes the strategy to build a secure, end-to-end encrypted (E2EE) Android application and local Python backend. The app supports multi-user communication, meeting scheduling, and content sharing in shared spaces and direct messages, with full client-side encryption.

## Technical Architecture
- **Local Backend (Python/FastAPI)**:
  - User registration & public key registry.
  - Space/Channel creation & membership tracking.
  - Message relay (DMs and channel messages) for encrypted payloads.
  - Encrypted space key registry (allowing members to retrieve the space's symmetric key encrypted under their public key).
  - Encrypted file upload/download storage.
- **Android Client (Kotlin/Java)**:
  - Client-side cryptographic engine (ECDH for key exchange, AES-GCM for payload encryption/decryption, PBKDF2 for password hashing / local storage encryption).
  - Local SQLite database (Room) for caching decrypted messages, spaces, and meetings.
  - Network client interacting with the backend API.
  - Unit and integration tests (JUnit/Robolectric) simulating multiple clients interacting through the backend to verify crypto operations, communication flows, meetings, and file sharing.

## Test Strategy (Dual Track)
- **E2E Testing Track**:
  - Independent track building a comprehensive black-box integration test suite in Python/Node.js or Kotlin simulating real multi-client networks.
  - Tiers of tests:
    - Tier 1: Feature Coverage (User registry, DM, Spaces, Meetings, Content Sharing).
    - Tier 2: Boundary/Corner Cases (Invalid keys, empty payloads, large files, unauthorized access).
    - Tier 3: Cross-Feature Combinations (Meetings in Spaces with file attachments).
    - Tier 4: Real-World Scenarios (Multi-user join/leave, key derivation verification, wire interception proving backend cannot decrypt).
- **Implementation Track**:
  - Sub-orchestrators and workers implementing each module.
  - Continuous unit and integration tests written in Kotlin (Android unit/Robolectric) and Python (backend tests).
  - Integration with E2E test suite to prove correctness.

## Milestones
1. **Milestone 1: E2E Test Suite Design (E2E Track)**
   - Create test harness, define formats, write tests for Tiers 1-4.
   - Outputs: `TEST_READY.md`, test cases, test runner.
2. **Milestone 2: Backend & Cryptographic Core**
   - Create local FastAPI backend with user registry, public key storage, message relay, and encrypted file storage.
   - Implement client-side cryptographic library (standard Java/Kotlin Cryptography Architecture) for ECDH key exchange and AES-GCM encryption/decryption.
   - Verification: Backend unit tests and cryptographic core verification tests.
3. **Milestone 3: Space Management & Direct Messaging**
   - Implement Android client core: Space creation/joining, user lookup, private messaging.
   - Key distribution for spaces: Creator encrypts space symmetric key for new members using their public keys.
   - Verification: Standard JUnit/Robolectric tests simulating space joining, key exchange, and DM/Space message relay.
4. **Milestone 4: Meeting Scheduling & Content Sharing**
   - Implement meeting scheduling client-side (JSON serialization, encryption with space/DM key, relay, parsing).
   - Implement content sharing: client-side file encryption with random AES key, uploading file ciphertext to backend, sharing file key encrypted with space/DM key.
   - Verification: Automated tests for meeting parsing and content encryption/decryption.
5. **Milestone 5: E2E Integration, Coverage Hardening & Verification**
   - Run E2E test suite against full app + backend.
   - Phase 2: Challenger generates adversarial test cases (white-box gap coverage).
   - Forensic audit verification.
   - Final victory claim.
