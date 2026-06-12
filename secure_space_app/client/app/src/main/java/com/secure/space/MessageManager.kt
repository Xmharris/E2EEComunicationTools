package com.secure.space

import com.google.gson.Gson
import com.secure.space.api.ApiClient
import com.secure.space.crypto.CryptoEngine
import com.secure.space.model.*
import java.io.IOException
import java.security.KeyPair
import java.security.PublicKey
import java.security.SecureRandom
import java.time.format.DateTimeFormatter

data class DecryptedMessage(
    val message: Message,
    val decryptedPayload: String
)

class MessageManager(
    val userId: String,
    val apiClient: ApiClient = ApiClient()
) {
    val keyPair: KeyPair = CryptoEngine.generateKeyPair("X25519")
    val publicKeyPem: String = CryptoEngine.serializePublicKeyToPem(keyPair.public)
    val spaceKeys = mutableMapOf<String, ByteArray>()

    private val gson = Gson()

    fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }

    fun String.hexToByteArray(): ByteArray {
        require(length % 2 == 0) { "Must have an even length" }
        val result = ByteArray(length / 2)
        for (i in 0 until length step 2) {
            result[i / 2] = substring(i, i + 2).toInt(16).toByte()
        }
        return result
    }

    fun register(): RegisterResponse {
        require(userId.isNotBlank()) { "Username cannot be empty" }
        require(userId.length <= 100) { "Username too long" }
        require(userId.matches(Regex("^[a-zA-Z0-9_-]+$"))) { "Username contains invalid characters" }
        return apiClient.registerUser(UserRegisterRequest(userId, publicKeyPem))
    }

    private fun getPeerPublicKey(peerId: String): PublicKey {
        val users = apiClient.getUsers()
        val user = users.find { it.userId == peerId }
            ?: throw IOException("User $peerId not found")
        return CryptoEngine.deserializePublicKeyFromPem(user.publicKey, "X25519")
    }

    private fun deriveSharedKey(peerPublicKey: PublicKey): ByteArray {
        return CryptoEngine.deriveSharedKey(
            privateKey = keyPair.private,
            peerPublicKey = peerPublicKey,
            salt = null,
            info = "secure-space-e2ee-key-agreement".toByteArray()
        )
    }

    fun createSpace(spaceId: String): SpaceCreateResponse {
        require(spaceId.isNotBlank()) { "Space ID cannot be empty" }
        val spaceKey = ByteArray(32).apply { SecureRandom().nextBytes(this) }
        spaceKeys[spaceId] = spaceKey

        val response = apiClient.createSpace(SpaceCreateRequest(spaceId, userId))
        addMemberToSpace(spaceId, userId)
        return response
    }

    fun addMemberToSpace(spaceId: String, memberId: String): AddMemberResponse {
        val spaceKey = spaceKeys[spaceId]
            ?: throw IllegalStateException("Space key for '$spaceId' not found locally")
        val memberPublicKey = getPeerPublicKey(memberId)
        val sharedKey = deriveSharedKey(memberPublicKey)
        val encryptedKeyHex = CryptoEngine.encryptAesGcm(sharedKey, spaceKey).toHex()
        return apiClient.addMember(AddMemberRequest(spaceId, memberId, encryptedKeyHex))
    }

    fun joinSpace(spaceId: String): ByteArray {
        val response = apiClient.getSpaceKey(spaceId, userId)
        val creatorPublicKey = getPeerPublicKey(response.creatorId)
        val sharedKey = deriveSharedKey(creatorPublicKey)
        val spaceKey = CryptoEngine.decryptAesGcm(sharedKey, response.encryptedKey.hexToByteArray())
        spaceKeys[spaceId] = spaceKey
        return spaceKey
    }

    fun sendDirectMessage(recipientId: String, text: String): SendMessageResponse {
        require(text.isNotBlank()) { "Encrypted payload cannot be empty" }
        require(recipientId != userId) { "Cannot send DM to self" }
        val recipientPublicKey = getPeerPublicKey(recipientId)
        val sharedKey = deriveSharedKey(recipientPublicKey)
        val encryptedPayload = CryptoEngine.encryptAesGcm(sharedKey, text.toByteArray(Charsets.UTF_8)).toHex()
        return apiClient.sendMessage(
            MessageSendRequest(
                senderId = userId,
                recipientId = recipientId,
                payloadType = "text",
                encryptedPayload = encryptedPayload
            )
        )
    }

    fun receiveDirectMessages(): List<DecryptedMessage> {
        val messages = apiClient.getMessages(userId = userId, spaceId = null)
        val decryptedList = mutableListOf<DecryptedMessage>()
        for (msg in messages) {
            if (msg.spaceId == null) {
                val peerId = if (msg.senderId == userId) msg.recipientId!! else msg.senderId
                val peerPublicKey = getPeerPublicKey(peerId)
                val sharedKey = deriveSharedKey(peerPublicKey)
                val decryptedBytes = CryptoEngine.decryptAesGcm(sharedKey, msg.encryptedPayload.hexToByteArray())
                val decryptedText = String(decryptedBytes, Charsets.UTF_8)
                decryptedList.add(DecryptedMessage(msg, decryptedText))
            }
        }
        return decryptedList
    }

    fun sendSpaceMessage(spaceId: String, text: String): SendMessageResponse {
        require(text.isNotBlank()) { "Encrypted payload cannot be empty" }
        val spaceKey = spaceKeys[spaceId]
            ?: throw IllegalStateException("No key for space $spaceId found locally")
        val encryptedPayload = CryptoEngine.encryptAesGcm(spaceKey, text.toByteArray(Charsets.UTF_8)).toHex()
        return apiClient.sendMessage(
            MessageSendRequest(
                senderId = userId,
                spaceId = spaceId,
                payloadType = "text",
                encryptedPayload = encryptedPayload
            )
        )
    }

    fun receiveSpaceMessages(spaceId: String): List<DecryptedMessage> {
        val spaceKey = spaceKeys[spaceId]
            ?: throw IllegalStateException("No key for space $spaceId found locally")
        val messages = apiClient.getMessages(userId = userId, spaceId = spaceId)
        val decryptedList = mutableListOf<DecryptedMessage>()
        for (msg in messages) {
            val decryptedBytes = CryptoEngine.decryptAesGcm(spaceKey, msg.encryptedPayload.hexToByteArray())
            val decryptedText = String(decryptedBytes, Charsets.UTF_8)
            decryptedList.add(DecryptedMessage(msg, decryptedText))
        }
        return decryptedList
    }

    fun scheduleMeeting(targetId: String, isSpace: Boolean, meetingMetadata: MeetingMetadata): SendMessageResponse {
        require(meetingMetadata.title.isNotBlank()) { "Missing required field: title" }
        require(meetingMetadata.time.isNotBlank()) { "Missing required field: time" }
        require(meetingMetadata.location.isNotBlank()) { "Missing required field: location" }

        // Validate time format (ISO)
        val timeStr = meetingMetadata.time
        val normalizedTime = if (timeStr.endsWith("Z")) {
            timeStr.substring(0, timeStr.length - 1) + "+00:00"
        } else {
            timeStr
        }
        try {
            DateTimeFormatter.ISO_DATE_TIME.parse(normalizedTime)
        } catch (e: Exception) {
            throw IllegalArgumentException("Invalid date format: $timeStr", e)
        }

        val metadataJson = gson.toJson(meetingMetadata)
        val payloadBytes = metadataJson.toByteArray(Charsets.UTF_8)

        val encryptedPayload = if (isSpace) {
            val spaceKey = spaceKeys[targetId]
                ?: throw IllegalStateException("No key for space $targetId found locally")
            CryptoEngine.encryptAesGcm(spaceKey, payloadBytes).toHex()
        } else {
            val recipientPublicKey = getPeerPublicKey(targetId)
            val sharedKey = deriveSharedKey(recipientPublicKey)
            CryptoEngine.encryptAesGcm(sharedKey, payloadBytes).toHex()
        }

        return apiClient.sendMessage(
            MessageSendRequest(
                senderId = userId,
                spaceId = if (isSpace) targetId else null,
                recipientId = if (!isSpace) targetId else null,
                payloadType = "meeting",
                encryptedPayload = encryptedPayload
            )
        )
    }

    fun decryptMeeting(message: Message): MeetingMetadata {
        val decryptedBytes = if (message.spaceId != null) {
            val spaceKey = spaceKeys[message.spaceId]
                ?: throw IllegalStateException("No key for space ${message.spaceId} found locally")
            CryptoEngine.decryptAesGcm(spaceKey, message.encryptedPayload.hexToByteArray())
        } else {
            val peerId = if (message.senderId == userId) message.recipientId!! else message.senderId
            val peerPublicKey = getPeerPublicKey(peerId)
            val sharedKey = deriveSharedKey(peerPublicKey)
            CryptoEngine.decryptAesGcm(sharedKey, message.encryptedPayload.hexToByteArray())
        }
        val metadataJson = String(decryptedBytes, Charsets.UTF_8)
        return gson.fromJson(metadataJson, MeetingMetadata::class.java)
    }

    fun shareFile(targetId: String, isSpace: Boolean, fileName: String, fileBytes: ByteArray): SendMessageResponse {
        require(fileBytes.isNotEmpty()) { "Cannot upload empty file" }
        // 1. Generate AES-256 file key
        val fileKey = ByteArray(32).apply { SecureRandom().nextBytes(this) }

        // 2. Encrypt file bytes (which naturally prepends 12-byte IV)
        val encryptedFileBytes = CryptoEngine.encryptAesGcm(fileKey, fileBytes)

        // 3. Upload to backend
        val uploadResponse = apiClient.uploadFile(
            fileBytes = encryptedFileBytes,
            fileName = fileName,
            userId = userId,
            spaceId = if (isSpace) targetId else null,
            recipientId = if (!isSpace) targetId else null
        )
        val fileId = uploadResponse.fileId

        // 4. Encrypt file key under channel key
        val channelKey = if (isSpace) {
            spaceKeys[targetId]
                ?: throw IllegalStateException("No key for space $targetId found locally")
        } else {
            val recipientPublicKey = getPeerPublicKey(targetId)
            deriveSharedKey(recipientPublicKey)
        }
        val encryptedFileKeyHex = CryptoEngine.encryptAesGcm(channelKey, fileKey).toHex()

        // 5. Encrypt metadata under channel key
        val fileMetadata = FileMetadata(
            fileId = fileId,
            fileName = fileName,
            encryptedFileKey = encryptedFileKeyHex
        )
        val metadataJson = gson.toJson(fileMetadata)
        val encryptedPayload = CryptoEngine.encryptAesGcm(channelKey, metadataJson.toByteArray(Charsets.UTF_8)).toHex()

        // 6. Send message
        return apiClient.sendMessage(
            MessageSendRequest(
                senderId = userId,
                spaceId = if (isSpace) targetId else null,
                recipientId = if (!isSpace) targetId else null,
                payloadType = "file",
                encryptedPayload = encryptedPayload
            )
        )
    }

    fun decryptFileMetadata(message: Message): FileMetadata {
        val channelKey = if (message.spaceId != null) {
            spaceKeys[message.spaceId]
                ?: throw IllegalStateException("No key for space ${message.spaceId} found locally")
        } else {
            val peerId = if (message.senderId == userId) message.recipientId!! else message.senderId
            val peerPublicKey = getPeerPublicKey(peerId)
            deriveSharedKey(peerPublicKey)
        }
        val decryptedBytes = CryptoEngine.decryptAesGcm(channelKey, message.encryptedPayload.hexToByteArray())
        val metadataJson = String(decryptedBytes, Charsets.UTF_8)
        return gson.fromJson(metadataJson, FileMetadata::class.java)
    }

    fun downloadAndDecryptFile(fileId: String, encryptedFileKeyHex: String, spaceId: String?, peerId: String?): ByteArray {
        val channelKey = if (spaceId != null) {
            spaceKeys[spaceId]
                ?: throw IllegalStateException("No key for space $spaceId found locally")
        } else {
            val resolvedPeerId = peerId ?: throw IllegalArgumentException("Missing peerId for DM file decryption")
            val peerPublicKey = getPeerPublicKey(resolvedPeerId)
            deriveSharedKey(peerPublicKey)
        }
        // Decrypt the file key
        val fileKey = CryptoEngine.decryptAesGcm(channelKey, encryptedFileKeyHex.hexToByteArray())
        // Download the encrypted file bytes
        val encryptedFileBytes = apiClient.downloadFile(fileId, userId)
        // Decrypt file bytes
        return CryptoEngine.decryptAesGcm(fileKey, encryptedFileBytes)
    }

    fun leaveSpace(spaceId: String): LeaveSpaceResponse {
        val response = apiClient.leaveSpace(LeaveSpaceRequest(spaceId, userId))
        spaceKeys.remove(spaceId)
        return response
    }
}
