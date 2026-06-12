package com.secure.space

import com.secure.space.api.ApiClient
import com.secure.space.model.*
import org.junit.Assert.*
import org.junit.Assume
import org.junit.Before
import org.junit.Test
import java.io.IOException
import java.net.Socket

class MessageManagerTest {

    private lateinit var mockClient: MockApiClient

    @Before
    fun setUp() {
        mockClient = MockApiClient()
    }

    private fun isBackendRunning(): Boolean {
        return try {
            Socket("127.0.0.1", 8089).use { true }
        } catch (e: Exception) {
            false
        }
    }

    // ==========================================
    // LOCAL UNIT TESTS (Offline / In-Memory Mock)
    // ==========================================

    @Test
    fun testUnitRegistration() {
        val manager = MessageManager("alice", mockClient)
        val response = manager.register()
        assertEquals("registered", response.status)
        assertEquals("alice", response.userId)

        val users = mockClient.getUsers()
        assertEquals(1, users.size)
        assertEquals("alice", users[0].userId)
        assertNotNull(users[0].publicKey)
    }

    @Test
    fun testUnitRegistrationValidation() {
        // Test empty username
        try {
            val manager = MessageManager("", mockClient)
            manager.register()
            fail("Should have failed for empty username")
        } catch (e: IllegalArgumentException) {
            // Success
        }

        // Test invalid characters
        try {
            val manager = MessageManager("alice@bob", mockClient)
            manager.register()
            fail("Should have failed for invalid characters")
        } catch (e: IllegalArgumentException) {
            // Success
        }

        // Test extremely long username
        try {
            val manager = MessageManager("a".repeat(101), mockClient)
            manager.register()
            fail("Should have failed for long username")
        } catch (e: IllegalArgumentException) {
            // Success
        }
    }

    @Test
    fun testUnitSpaceCreationAndMembers() {
        val alice = MessageManager("alice", mockClient)
        val bob = MessageManager("bob", mockClient)

        alice.register()
        bob.register()

        val spaceId = "project-x"
        alice.createSpace(spaceId)

        // Verify Alice has the key
        val aliceKey = alice.spaceKeys[spaceId]
        assertNotNull(aliceKey)

        // Add Bob
        alice.addMemberToSpace(spaceId, "bob")

        // Bob joins space
        val bobKey = bob.joinSpace(spaceId)
        assertArrayEquals(aliceKey, bobKey)

        // Verify members list
        val members = mockClient.getSpaceMembers(spaceId).members
        assertTrue(members.contains("alice"))
        assertTrue(members.contains("bob"))
    }

    @Test
    fun testUnitDirectMessaging() {
        val alice = MessageManager("alice", mockClient)
        val bob = MessageManager("bob", mockClient)

        alice.register()
        bob.register()

        alice.sendDirectMessage("bob", "Hello Bob, this is a secret!")

        val bobDms = bob.receiveDirectMessages()
        assertEquals(1, bobDms.size)
        assertEquals("Hello Bob, this is a secret!", bobDms[0].decryptedPayload)
        assertEquals("alice", bobDms[0].message.senderId)
        assertEquals("bob", bobDms[0].message.recipientId)

        // Bob replies
        bob.sendDirectMessage("alice", "Hi Alice, received loud and clear!")
        val aliceDms = alice.receiveDirectMessages()
        assertEquals(1, aliceDms.size)
        assertEquals("Hi Alice, received loud and clear!", aliceDms[0].decryptedPayload)
    }

    @Test
    fun testUnitSpaceMessaging() {
        val alice = MessageManager("alice", mockClient)
        val bob = MessageManager("bob", mockClient)

        alice.register()
        bob.register()

        val spaceId = "secure-channel"
        alice.createSpace(spaceId)
        alice.addMemberToSpace(spaceId, "bob")
        bob.joinSpace(spaceId)

        alice.sendSpaceMessage(spaceId, "Welcome to the space!")

        val bobMessages = bob.receiveSpaceMessages(spaceId)
        assertEquals(1, bobMessages.size)
        assertEquals("Welcome to the space!", bobMessages[0].decryptedPayload)
        assertEquals("alice", bobMessages[0].message.senderId)
        assertEquals(spaceId, bobMessages[0].message.spaceId)
    }

    @Test
    fun testUnitSchedulingMeetings() {
        val alice = MessageManager("alice", mockClient)
        val bob = MessageManager("bob", mockClient)

        alice.register()
        bob.register()

        val meeting = MeetingMetadata(
            title = "Secret Launch",
            time = "2026-06-12T10:00:00Z",
            location = "Room 101",
            description = "Let's align on client rollout details."
        )

        // DM Meeting
        alice.scheduleMeeting("bob", isSpace = false, meeting)

        val bobDms = bob.apiClient.getMessages("bob", null)
        val meetingMsg = bobDms.find { it.payloadType == "meeting" }
        assertNotNull(meetingMsg)

        val decryptedMeeting = bob.decryptMeeting(meetingMsg!!)
        assertEquals("Secret Launch", decryptedMeeting.title)
        assertEquals("2026-06-12T10:00:00Z", decryptedMeeting.time)
        assertEquals("Room 101", decryptedMeeting.location)
        assertEquals("Let's align on client rollout details.", decryptedMeeting.description)

        // Test invalid time format validation
        try {
            val badMeeting = MeetingMetadata("Bad Time", "not-a-date", "Online")
            alice.scheduleMeeting("bob", isSpace = false, badMeeting)
            fail("Should have failed for invalid date-time format")
        } catch (e: IllegalArgumentException) {
            // Success
        }
    }

    @Test
    fun testUnitFileSharing() {
        val alice = MessageManager("alice", mockClient)
        val bob = MessageManager("bob", mockClient)

        alice.register()
        bob.register()

        val originalData = "Important confidential file content".toByteArray()
        alice.shareFile("bob", isSpace = false, fileName = "doc.txt", fileBytes = originalData)

        // Bob gets message
        val bobMessages = bob.apiClient.getMessages("bob", null)
        val fileMessage = bobMessages.find { it.payloadType == "file" }
        assertNotNull(fileMessage)

        val metadata = bob.decryptFileMetadata(fileMessage!!)
        assertEquals("doc.txt", metadata.fileName)

        val downloadedBytes = bob.downloadAndDecryptFile(
            fileId = metadata.fileId,
            encryptedFileKeyHex = metadata.encryptedFileKey,
            spaceId = null,
            peerId = "alice"
        )
        assertArrayEquals(originalData, downloadedBytes)
    }

    @Test
    fun testUnitLeaveSpace() {
        val alice = MessageManager("alice", mockClient)
        val bob = MessageManager("bob", mockClient)

        alice.register()
        bob.register()

        val spaceId = "leaver-space"
        alice.createSpace(spaceId)
        alice.addMemberToSpace(spaceId, "bob")
        bob.joinSpace(spaceId)

        // Bob leaves
        bob.leaveSpace(spaceId)

        assertFalse(bob.spaceKeys.containsKey(spaceId))

        val members = mockClient.getSpaceMembers(spaceId).members
        assertFalse(members.contains("bob"))
    }

    // ==========================================
    // INTEGRATION TESTS (Run against real backend if running)
    // ==========================================

    @Test
    fun testIntegrationAllFlows() {
        val running = isBackendRunning()
        if (!running) {
            println("Real backend is not running on 8089. Skipping integration tests.")
        }
        Assume.assumeTrue("Skipping integration test: real backend is not running on 8089", running)

        val realClient = ApiClient("http://127.0.0.1:8089")
        realClient.resetBackend()

        val suffix = System.currentTimeMillis().toString()
        val aliceId = "alice_$suffix"
        val bobId = "bob_$suffix"

        val alice = MessageManager(aliceId, realClient)
        val bob = MessageManager(bobId, realClient)

        // 1. Register
        alice.register()
        bob.register()

        // 2. Space Management
        val spaceId = "space_$suffix"
        alice.createSpace(spaceId)
        alice.addMemberToSpace(spaceId, bobId)
        bob.joinSpace(spaceId)

        // 3. DM
        alice.sendDirectMessage(bobId, "Direct secure message")
        val bobDms = bob.receiveDirectMessages()
        assertTrue(bobDms.any { it.decryptedPayload == "Direct secure message" })

        // 4. Space messaging
        bob.sendSpaceMessage(spaceId, "Hello space members")
        val aliceSpaceMsgs = alice.receiveSpaceMessages(spaceId)
        assertTrue(aliceSpaceMsgs.any { it.decryptedPayload == "Hello space members" })

        // 5. Meetings
        val meeting = MeetingMetadata(
            title = "Board Sync",
            time = "2026-06-12T15:00:00Z",
            location = "Secure Room A"
        )
        alice.scheduleMeeting(spaceId, isSpace = true, meeting)
        val bobMsgs = bob.apiClient.getMessages(bobId, spaceId)
        val meetingMsg = bobMsgs.find { it.payloadType == "meeting" }
        assertNotNull(meetingMsg)
        val decryptedMeeting = bob.decryptMeeting(meetingMsg!!)
        assertEquals("Board Sync", decryptedMeeting.title)

        // 6. File sharing
        val fileBytes = "Sensitive project roadmap".toByteArray()
        alice.shareFile(spaceId, isSpace = true, fileName = "roadmap.txt", fileBytes = fileBytes)

        val bobSpaceMsgs = bob.apiClient.getMessages(bobId, spaceId)
        val fileMsg = bobSpaceMsgs.find { it.payloadType == "file" }
        assertNotNull(fileMsg)
        val fileMetadata = bob.decryptFileMetadata(fileMsg!!)
        assertEquals("roadmap.txt", fileMetadata.fileName)

        val downloadedBytes = bob.downloadAndDecryptFile(
            fileId = fileMetadata.fileId,
            encryptedFileKeyHex = fileMetadata.encryptedFileKey,
            spaceId = spaceId,
            peerId = null
        )
        assertArrayEquals(fileBytes, downloadedBytes)

        // 7. Leave space
        bob.leaveSpace(spaceId)
        val finalMembers = realClient.getSpaceMembers(spaceId).members
        assertFalse(finalMembers.contains(bobId))
    }

    // ==========================================
    // MOCK API CLIENT CLASS
    // ==========================================

    class MockApiClient : ApiClient("http://mock-backend") {
        private val users = mutableListOf<User>()
        private val spaces = mutableListOf<SpaceCreateRequest>()
        private val spaceKeys = mutableMapOf<Pair<String, String>, String>() // (spaceId, userId) -> encryptedKey
        private val spaceCreators = mutableMapOf<String, String>() // spaceId -> creatorId
        private val messages = mutableListOf<Message>()
        private val files = mutableMapOf<String, ByteArray>() // fileId -> bytes
        private var messageIdCounter = 1

        override fun registerUser(requestDto: UserRegisterRequest): RegisterResponse {
            if (users.any { it.userId == requestDto.userId }) {
                throw IOException("Username already registered")
            }
            users.add(User(requestDto.userId, requestDto.publicKey))
            return RegisterResponse("registered", requestDto.userId)
        }

        override fun getUsers(): List<User> {
            return users
        }

        override fun createSpace(requestDto: SpaceCreateRequest): SpaceCreateResponse {
            if (spaces.any { it.spaceId == requestDto.spaceId }) {
                throw IOException("Space already exists")
            }
            spaces.add(requestDto)
            spaceCreators[requestDto.spaceId] = requestDto.creatorId
            return SpaceCreateResponse("created", requestDto.spaceId)
        }

        override fun addMember(requestDto: AddMemberRequest): AddMemberResponse {
            val key = Pair(requestDto.spaceId, requestDto.userId)
            if (spaceKeys.containsKey(key)) {
                throw IOException("User already member of space")
            }
            spaceKeys[key] = requestDto.encryptedKey
            return AddMemberResponse("added", requestDto.spaceId, requestDto.userId)
        }

        override fun leaveSpace(requestDto: LeaveSpaceRequest): LeaveSpaceResponse {
            val key = Pair(requestDto.spaceId, requestDto.userId)
            if (!spaceKeys.containsKey(key)) {
                throw IOException("User is not a member of the space")
            }
            spaceKeys.remove(key)
            return LeaveSpaceResponse("left", requestDto.spaceId, requestDto.userId)
        }

        override fun getSpaceKey(spaceId: String, userId: String): SpaceKeyResponse {
            val creatorId = spaceCreators[spaceId] ?: throw IOException("Space not found")
            val encryptedKey = spaceKeys[Pair(spaceId, userId)] ?: throw IOException("Key not found")
            return SpaceKeyResponse(spaceId, userId, encryptedKey, creatorId)
        }

        override fun getSpaceMembers(spaceId: String): SpaceMembersResponse {
            val members = spaceKeys.keys.filter { it.first == spaceId }.map { it.second }
            return SpaceMembersResponse(spaceId, members)
        }

        override fun sendMessage(requestDto: MessageSendRequest): SendMessageResponse {
            val msg = Message(
                id = messageIdCounter++,
                senderId = requestDto.senderId,
                recipientId = requestDto.recipientId,
                spaceId = requestDto.spaceId,
                payloadType = requestDto.payloadType,
                encryptedPayload = requestDto.encryptedPayload
            )
            messages.add(msg)
            return SendMessageResponse("sent", msg.id)
        }

        override fun getMessages(userId: String, spaceId: String?): List<Message> {
            if (spaceId != null) {
                return messages.filter { it.spaceId == spaceId }
            }
            return messages.filter { it.spaceId == null && (it.senderId == userId || it.recipientId == userId) }
        }

        override fun uploadFile(
            fileBytes: ByteArray,
            fileName: String,
            userId: String?,
            spaceId: String?,
            recipientId: String?
        ): UploadFileResponse {
            val fileId = java.util.UUID.randomUUID().toString()
            files[fileId] = fileBytes
            return UploadFileResponse(fileId)
        }

        override fun downloadFile(fileId: String, userId: String?): ByteArray {
            return files[fileId] ?: throw IOException("File not found")
        }

        override fun resetBackend() {
            users.clear()
            spaces.clear()
            spaceKeys.clear()
            spaceCreators.clear()
            messages.clear()
            files.clear()
        }
    }
}
