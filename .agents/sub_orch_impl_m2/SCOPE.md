# Scope: Milestone 2 - Secure Space Android Client Core

## Architecture
- Codebase language: Kotlin (JVM target).
- Directory structure:
  - Source: `secure_space_app/client/app/src/main/java/com/secure/space/`
    - `api/`: API wrappers / HTTP network client.
    - `model/`: Data classes (User, Space, Message).
    - `crypto/`: Cryptographic operations (`CryptoEngine.kt` already exists).
    - Root of package: `MessageManager.kt` or similar coordination logic.
  - Tests: `secure_space_app/client/app/src/test/java/com/secure/space/`
    - Unit and integration tests for serialization, client API wrappers, key agreement, wrapping, and messaging.

## Interface Contracts
- **ApiClient/NetworkManager**:
  - `registerUser(userId: String, publicKeyPem: String): RegisterResponse`
  - `getUserDirectory(): List<User>`
  - `createSpace(spaceId: String, creatorId: String): CreateSpaceResponse`
  - `addMemberToSpace(spaceId: String, memberId: String, encryptedKeyHex: String): AddMemberResponse`
  - `getSpaceKey(spaceId: String, userId: String): SpaceKeyResponse`
  - `sendSpaceMessage(senderId: String, spaceId: String, encryptedPayload: String): SendMessageResponse`
  - `sendDirectMessage(senderId: String, recipientId: String, encryptedPayload: String): SendMessageResponse`
  - `getMessages(userId: String, spaceId: String? = null): List<Message>`
  - `getSpaceMembers(spaceId: String): List<String>`
  - `leaveSpace(spaceId: String, userId: String): LeaveSpaceResponse`
- **Data Models**:
  - `User(userId: String, publicKey: String)`
  - `Space(spaceId: String, creatorId: String)`
  - `Message(senderId: String, recipientId: String?, spaceId: String?, payloadType: String, encryptedPayload: String)`
- **MessageManager/SpaceManager**:
  - Encapsulates state (current user keypair, cached space keys).
  - Handles key generation, key agreement, encryption, decryption, and API requests.

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | Exploration & Design | Discover environment capabilities, JDK/Gradle config, design models/API/Manager | None | DONE (c12b1672-228c-47e6-a4f6-fb25f933a62b) |
| 2 | Implementation | Write build.gradle, settings.gradle, models, ApiClient, MessageManager | M1 | DONE (1b7bd885-d7eb-438b-944e-f8606da61aa0) |
| 3 | Verification | Write JUnit tests, compile and execute build & tests via Worker | M2 | DONE (Reviewers: 9067a690-0541-4379-91be-4b2ca770b2b3, 4447f449-f219-4a14-84b7-18c8fc8b0743; Challengers: a71c541b-ce61-4f58-a64f-616aeb9a4095, c42f5746-0e94-4bd9-b288-b853b3859694; Auditor: fc015323-9854-47a4-be1c-f92fea45e3a3) |
| 4 | Final Integration | Confirm behavior conforms to E2E tests and mock backend | M3 | DONE (Worker Gen 2: 5fd54793-e2c9-440e-b40c-95ef5b9b619b) |
