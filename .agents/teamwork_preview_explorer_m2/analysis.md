# Analysis - Secure Space Android Client Design

## 1. Backend REST Endpoints & Schemas
Based on the examination of `secure_space_app/backend/app/main.py`, the backend exposes the following endpoints:

| Method | Endpoint | Request Schema / Params | Response Format | Description |
|---|---|---|---|---|
| **POST** | `/api/reset` | None | `{"status": "reset"}` | Resets the SQLite database (deletes all rows). |
| **POST** | `/api/users/register` | `UserRegisterRequest` JSON: `{"user_id": str, "public_key": str}` | `{"status": "registered", "user_id": str}` | Registers a new user. Rejects duplicates, empty user IDs, IDs > 100 chars, invalid characters, or invalid PEM public keys with `400 Bad Request`. |
| **GET** | `/api/users` | None | `List` of `{"user_id": str, "public_key": str}` | Retrieves the registry of registered users. |
| **POST** | `/api/spaces/create` | `SpaceCreateRequest` JSON: `{"space_id": str, "creator_id": str}` | `{"status": "created", "space_id": str}` | Creates a new space. Rejects if space exists (`400`) or creator is not registered (`404`). |
| **POST** | `/api/spaces/add_member` | `AddMemberRequest` JSON: `{"space_id": str, "user_id": str, "encrypted_key": str}` | `{"status": "added", "space_id": str, "user_id": str}` | Adds a member to a space. Rejects if space/user not found (`404`) or member already exists (`400`). |
| **POST** | `/api/spaces/leave` | `LeaveSpaceRequest` JSON: `{"space_id": str, "user_id": str}` | `{"status": "left", "space_id": str, "user_id": str}` | Removes a member from a space. Rejects if space not found or user is not a member (`404`). |
| **GET** | `/api/spaces/{space_id}/key` | Query param: `user_id` | `{"space_id": str, "user_id": str, "encrypted_key": str, "creator_id": str}` | Fetches the encrypted space key for the requested user. Rejects if space/key is not found (`404`). |
| **GET** | `/api/spaces/{space_id}/members` | None | `{"space_id": str, "members": List[str]}` | Fetches the member list for a space. Rejects if space not found (`404`). |
| **POST** | `/api/messages/send` | `MessageSendRequest` JSON: `{"sender_id": str, "recipient_id": str?, "space_id": str?, "payload_type": str, "encrypted_payload": str}` | `{"status": "sent", "message_id": int}` | Sends a DM or a space message. `payload_type` can be `"text"`, `"meeting"`, or `"file"`. Rejects missing fields (`400`), unregistered sender (`401`), non-member sending to space (`403`), unregistered DM recipient (`404`), or DM to self (`400`). |
| **GET** | `/api/messages` | Query params: `user_id` (req), `space_id` (opt) | `List` of `{"id": int, "sender_id": str, "recipient_id": str?, "space_id": str?, "payload_type": str, "encrypted_payload": str}` | Retrieves messages. If `space_id` is specified, returns space messages (checks membership, else `403`). Otherwise, returns DMs where user is sender or recipient. |
| **POST** | `/api/files/upload` | Form/Multipart: `file` file bytes. Query params: `user_id`, `space_id` (opt), `recipient_id` (opt) | `{"file_id": str}` | Uploads file bytes. Rejects if file is empty (`400`). |
| **GET** | `/api/files/download/{file_id}` | Query param: `user_id` | Octet-stream binary bytes | Downloads file bytes. Performs access control validation: allows if requester is uploader, a member of the space associated with the file, or the recipient of the DM associated with the file. Returns `403` or `404` otherwise. |

---

## 2. Environment Verification & Proposes Build Files

### System Environment Check
A check of the system environment indicates that standard developer command-line tools `java`, `javac`, and `gradle` are **not present** on the system `PATH`.
- `java`: Command not found
- `javac`: Command not found
- `gradle`: Command not found

For compile and test capability in the target execution environment, we propose a standard, self-contained Gradle project configuration that supports Kotlin compilation and JUnit 4 execution.

### Proposed `secure_space_app/client/build.gradle`
This configuration adds OkHttp (HTTP client), Gson (JSON parser), and JUnit 4 (testing framework) dependencies. It also defines custom source sets to map existing files in `app/src/main/java` and `app/src/test/java`.

```groovy
plugins {
    id 'org.jetbrains.kotlin.jvm' version '1.8.21'
}

group = 'com.secure.space'
version = '1.0-SNAPSHOT'

repositories {
    mavenCentral()
}

dependencies {
    // Kotlin Stdlib
    implementation "org.jetbrains.kotlin:kotlin-stdlib:1.8.21"
    
    // HTTP Client (OkHttp)
    implementation "com.squareup.okhttp3:okhttp:4.10.0"
    
    // JSON Serialization (Gson)
    implementation "com.google.code.gson:gson:2.10.1"
    
    // Testing
    testImplementation "junit:junit:4.13.2"
}

sourceSets {
    main {
        java {
            srcDirs = ['app/src/main/java']
        }
    }
    test {
        java {
            srcDirs = ['app/src/test/java']
        }
    }
}

test {
    useJUnit()
    testLogging {
        events "passed", "skipped", "failed"
    }
}
```

### Proposed `secure_space_app/client/settings.gradle`
```groovy
rootProject.name = 'secure-space-client'
```

---

## 3. Python Client Simulation Mapping to Kotlin

The Python simulation `ClientSim` (defined in `secure_space_app/tests/client_sim.py`) implements end-to-end cryptographic and networking protocols. Below is the mapped Kotlin structure, dividing the logic into **Data Models**, a helper **API Client**, and the **Client Manager** (which matches the client's state and methods).

### 3.1. Data Models (`com.secure.space.models`)
These models map directly to the JSON payloads expected by the backend and standard metadata formats.

```kotlin
package com.secure.space.models

import com.google.gson.annotations.SerializedName

data class User(
    @SerializedName("user_id") val userId: String,
    @SerializedName("public_key") val publicKey: String
)

data class UserRegisterRequest(
    @SerializedName("user_id") val userId: String,
    @SerializedName("public_key") val publicKey: String
)

data class RegisterResponse(
    @SerializedName("status") val status: String,
    @SerializedName("user_id") val userId: String
)

data class SpaceCreateRequest(
    @SerializedName("space_id") val spaceId: String,
    @SerializedName("creator_id") val creatorId: String
)

data class SpaceCreateResponse(
    @SerializedName("status") val status: String,
    @SerializedName("space_id") val spaceId: String
)

data class AddMemberRequest(
    @SerializedName("space_id") val spaceId: String,
    @SerializedName("user_id") val userId: String,
    @SerializedName("encrypted_key") val encryptedKey: String
)

data class AddMemberResponse(
    @SerializedName("status") val status: String,
    @SerializedName("space_id") val spaceId: String,
    @SerializedName("user_id") val userId: String
)

data class LeaveSpaceRequest(
    @SerializedName("space_id") val spaceId: String,
    @SerializedName("user_id") val userId: String
)

data class LeaveSpaceResponse(
    @SerializedName("status") val status: String,
    @SerializedName("space_id") val spaceId: String,
    @SerializedName("user_id") val userId: String
)

data class SpaceKeyResponse(
    @SerializedName("space_id") val spaceId: String,
    @SerializedName("user_id") val userId: String,
    @SerializedName("encrypted_key") val encryptedKey: String,
    @SerializedName("creator_id") val creatorId: String
)

data class SpaceMembersResponse(
    @SerializedName("space_id") val spaceId: String,
    @SerializedName("members") val members: List<String>
)

data class MessageSendRequest(
    @SerializedName("sender_id") val senderId: String,
    @SerializedName("recipient_id") val recipientId: String? = null,
    @SerializedName("space_id") val spaceId: String? = null,
    @SerializedName("payload_type") val payloadType: String,
    @SerializedName("encrypted_payload") val encryptedPayload: String
)

data class SendMessageResponse(
    @SerializedName("status") val status: String,
    @SerializedName("message_id") val messageId: Int
)

data class Message(
    @SerializedName("id") val id: Int,
    @SerializedName("sender_id") val senderId: String,
    @SerializedName("recipient_id") val recipientId: String?,
    @SerializedName("space_id") val spaceId: String?,
    @SerializedName("payload_type") val payloadType: String,
    @SerializedName("encrypted_payload") val encryptedPayload: String,
    @Transient var decryptedPayload: String? = null
)

data class UploadFileResponse(
    @SerializedName("file_id") val fileId: String
)

data class MeetingMetadata(
    @SerializedName("title") val title: String,
    @SerializedName("time") val time: String,
    @SerializedName("location") val location: String
)

data class FileMetadata(
    @SerializedName("file_id") val fileId: String,
    @SerializedName("file_name") val fileName: String,
    @SerializedName("encrypted_file_key") val encryptedFileKey: String
)
```

### 3.2. API Client Wrapper (`com.secure.space.api.SecureSpaceApiClient`)
Implements standard synchronous HTTP operations using OkHttp and Gson serialization.

```kotlin
package com.secure.space.api

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.secure.space.models.*
import okhttp3.*
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.RequestBody.Companion.toRequestBody
import java.io.IOException

class SecureSpaceApiClient(private val backendUrl: String) {
    private val client = OkHttpClient()
    private val gson = Gson()
    private val jsonMediaType = "application/json; charset=utf-8".toMediaTypeOrNull()

    private fun postRequest(path: String, bodyJson: String): String {
        val body = bodyJson.toRequestBody(jsonMediaType)
        val request = Request.Builder()
            .url("$backendUrl$path")
            .post(body)
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Unexpected code $response, body: ${response.body?.string()}")
            return response.body?.string() ?: throw IOException("Empty response body")
        }
    }

    fun register(userId: String, publicKeyPem: String): RegisterResponse {
        val req = UserRegisterRequest(userId, publicKeyPem)
        val resp = postRequest("/api/users/register", gson.toJson(req))
        return gson.fromJson(resp, RegisterResponse::class.java)
    }

    fun getUsers(): List<User> {
        val request = Request.Builder().url("$backendUrl/api/users").get().build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Unexpected code $response")
            val respStr = response.body?.string() ?: "[]"
            val listType = object : TypeToken<List<User>>() {}.type
            return gson.fromJson(respStr, listType)
        }
    }

    fun createSpace(spaceId: String, creatorId: String): SpaceCreateResponse {
        val req = SpaceCreateRequest(spaceId, creatorId)
        val resp = postRequest("/api/spaces/create", gson.toJson(req))
        return gson.fromJson(resp, SpaceCreateResponse::class.java)
    }

    fun addMember(spaceId: String, userId: String, encryptedKey: String): AddMemberResponse {
        val req = AddMemberRequest(spaceId, userId, encryptedKey)
        val resp = postRequest("/api/spaces/add_member", gson.toJson(req))
        return gson.fromJson(resp, AddMemberResponse::class.java)
    }

    fun leaveSpace(spaceId: String, userId: String): LeaveSpaceResponse {
        val req = LeaveSpaceRequest(spaceId, userId)
        val resp = postRequest("/api/spaces/leave", gson.toJson(req))
        return gson.fromJson(resp, LeaveSpaceResponse::class.java)
    }

    fun getSpaceKey(spaceId: String, userId: String): SpaceKeyResponse {
        val url = "$backendUrl/api/spaces/$spaceId/key".toHttpUrlOrNull()!!
            .newBuilder()
            .addQueryParameter("user_id", userId)
            .build()
        val request = Request.Builder().url(url).get().build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Unexpected code $response")
            val respStr = response.body?.string() ?: throw IOException("Empty body")
            return gson.fromJson(respStr, SpaceKeyResponse::class.java)
        }
    }

    fun getSpaceMembers(spaceId: String): SpaceMembersResponse {
        val request = Request.Builder().url("$backendUrl/api/spaces/$spaceId/members").get().build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Unexpected code $response")
            val respStr = response.body?.string() ?: throw IOException("Empty body")
            return gson.fromJson(respStr, SpaceMembersResponse::class.java)
        }
    }

    fun sendMessage(
        senderId: String,
        recipientId: String?,
        spaceId: String?,
        payloadType: String,
        encryptedPayload: String
    ): SendMessageResponse {
        val req = MessageSendRequest(senderId, recipientId, spaceId, payloadType, encryptedPayload)
        val resp = postRequest("/api/messages/send", gson.toJson(req))
        return gson.fromJson(resp, SendMessageResponse::class.java)
    }

    fun getMessages(userId: String, spaceId: String?): List<Message> {
        val urlBuilder = "$backendUrl/api/messages".toHttpUrlOrNull()!!
            .newBuilder()
            .addQueryParameter("user_id", userId)
        if (spaceId != null) {
            urlBuilder.addQueryParameter("space_id", spaceId)
        }
        val request = Request.Builder().url(urlBuilder.build()).get().build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Unexpected code $response")
            val respStr = response.body?.string() ?: "[]"
            val listType = object : TypeToken<List<Message>>() {}.type
            return gson.fromJson(respStr, listType)
        }
    }

    fun uploadFile(
        fileBytes: ByteArray,
        fileName: String,
        userId: String,
        spaceId: String?,
        recipientId: String?
    ): UploadFileResponse {
        val fileBody = RequestBody.create("application/octet-stream".toMediaTypeOrNull(), fileBytes)
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", fileName, fileBody)
            .build()
        
        val urlBuilder = "$backendUrl/api/files/upload".toHttpUrlOrNull()!!
            .newBuilder()
            .addQueryParameter("user_id", userId)
        if (spaceId != null) {
            urlBuilder.addQueryParameter("space_id", spaceId)
        }
        if (recipientId != null) {
            urlBuilder.addQueryParameter("recipient_id", recipientId)
        }

        val request = Request.Builder()
            .url(urlBuilder.build())
            .post(requestBody)
            .build()

        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Unexpected code $response")
            val respStr = response.body?.string() ?: throw IOException("Empty body")
            return gson.fromJson(respStr, UploadFileResponse::class.java)
        }
    }

    fun downloadFile(fileId: String, userId: String): ByteArray {
        val url = "$backendUrl/api/files/download/$fileId".toHttpUrlOrNull()!!
            .newBuilder()
            .addQueryParameter("user_id", userId)
            .build()
        val request = Request.Builder().url(url).get().build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) throw IOException("Unexpected code $response")
            return response.body?.bytes() ?: throw IOException("Empty body")
        }
    }
}
```

### 3.3. Secure Space Client Manager (`com.secure.space.SecureSpaceClient`)
Acts as the developer-facing manager handling local ECDH keys, shared secret derivations, metadata JSON serializations, and file/message cryptographic operations.

```kotlin
package com.secure.space

import com.google.gson.Gson
import com.secure.space.api.SecureSpaceApiClient
import com.secure.space.crypto.CryptoEngine
import com.secure.space.models.*
import java.security.KeyPair
import java.security.SecureRandom
import java.time.format.DateTimeFormatter
import java.time.Instant

class SecureSpaceClient(val userId: String, val backendUrl: String) {
    private val keyPair: KeyPair = CryptoEngine.generateKeyPair("X25519")
    val publicKeyPem: String = CryptoEngine.serializePublicKeyToPem(keyPair.public)
    val spaceKeys = mutableMapOf<String, ByteArray>()
    
    private val apiClient = SecureSpaceApiClient(backendUrl)
    private val gson = Gson()
    private val secureRandom = SecureRandom()

    // --- Helper Hex Functions ---
    private fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }
    private fun String.hexToByteArray(): ByteArray {
        require(length % 2 == 0) { "Hex string must have an even length" }
        return chunked(2).map { it.toInt(16).toByte() }.toByteArray()
    }

    fun register(): RegisterResponse {
        return apiClient.register(userId, publicKeyPem)
    }

    fun getPublicKeyPem(): String {
        return publicKeyPem
    }

    private fun getUserPublicKeyPem(peerId: String): String {
        val users = apiClient.getUsers()
        for (user in users) {
            if (user.userId == peerId) {
                return user.publicKey
            }
        }
        throw IllegalArgumentException("Public key for user '$peerId' not found on backend.")
    }

    private fun deriveSharedKey(peerPublicKeyPem: String): ByteArray {
        val peerPubKey = CryptoEngine.deserializePublicKeyFromPem(peerPublicKeyPem, "X25519")
        return CryptoEngine.deriveSharedKey(
            privateKey = keyPair.private,
            peerPublicKey = peerPubKey,
            salt = null,
            info = "secure-space-e2ee-key-agreement".toByteArray(Charsets.UTF_8),
            derivedKeyLength = 32,
            algorithm = "X25519"
        )
    }

    fun createSpace(spaceId: String): SpaceCreateResponse {
        val spaceKey = ByteArray(32).also { secureRandom.nextBytes(it) }
        spaceKeys[spaceId] = spaceKey
        
        val resp = apiClient.createSpace(spaceId, userId)
        addMemberToSpace(spaceId, userId)
        return resp
    }

    fun addMemberToSpace(spaceId: String, memberId: String): AddMemberResponse {
        val spaceKey = spaceKeys[spaceId] ?: throw IllegalArgumentException("Space key for '$spaceId' not found locally")
        val memberPubKeyPem = getUserPublicKeyPem(memberId)
        val sharedKey = deriveSharedKey(memberPubKeyPem)
        
        val encryptedKey = CryptoEngine.encryptAesGcm(sharedKey, spaceKey)
        val encryptedKeyHex = encryptedKey.toHex()
        
        return apiClient.addMember(spaceId, memberId, encryptedKeyHex)
    }

    fun joinSpace(spaceId: String): ByteArray {
        val keyData = apiClient.getSpaceKey(spaceId, userId)
        val creatorPubKeyPem = getUserPublicKeyPem(keyData.creatorId)
        val sharedKey = deriveSharedKey(creatorPubKeyPem)
        
        val spaceKey = CryptoEngine.decryptAesGcm(sharedKey, keyData.encryptedKey.hexToByteArray())
        spaceKeys[spaceId] = spaceKey
        return spaceKey
    }

    fun sendDm(recipientId: String, text: String): SendMessageResponse {
        val recipientPubKeyPem = getUserPublicKeyPem(recipientId)
        val sharedKey = deriveSharedKey(recipientPubKeyPem)
        
        val encryptedPayload = CryptoEngine.encryptAesGcm(sharedKey, text.toByteArray(Charsets.UTF_8)).toHex()
        return apiClient.sendMessage(userId, recipientId, null, "text", encryptedPayload)
    }

    fun receiveDms(): List<Message> {
        val messages = apiClient.getMessages(userId, null)
        val decryptedList = mutableListOf<Message>()
        for (msg in messages) {
            if (msg.spaceId == null) {
                val peerId = if (msg.senderId == userId) msg.recipientId!! else msg.senderId
                val peerPubKeyPem = getUserPublicKeyPem(peerId)
                val sharedKey = deriveSharedKey(peerPubKeyPem)
                
                val decryptedBytes = CryptoEngine.decryptAesGcm(sharedKey, msg.encryptedPayload.hexToByteArray())
                msg.decryptedPayload = String(decryptedBytes, Charsets.UTF_8)
                decryptedList.add(msg)
            }
        }
        return decryptedList
    }

    fun sendSpaceMessage(spaceId: String, text: String): SendMessageResponse {
        val spaceKey = spaceKeys[spaceId] ?: throw IllegalArgumentException("No key for space $spaceId found locally")
        val encryptedPayload = CryptoEngine.encryptAesGcm(spaceKey, text.toByteArray(Charsets.UTF_8)).toHex()
        return apiClient.sendMessage(userId, null, spaceId, "text", encryptedPayload)
    }

    fun receiveSpaceMessages(spaceId: String): List<Message> {
        val spaceKey = spaceKeys[spaceId] ?: throw IllegalArgumentException("No key for space $spaceId found locally")
        val messages = apiClient.getMessages(userId, spaceId)
        val decryptedList = mutableListOf<Message>()
        for (msg in messages) {
            val decryptedBytes = CryptoEngine.decryptAesGcm(spaceKey, msg.encryptedPayload.hexToByteArray())
            msg.decryptedPayload = String(decryptedBytes, Charsets.UTF_8)
            decryptedList.add(msg)
        }
        return decryptedList
    }

    fun scheduleMeeting(targetId: String, isSpace: Boolean, meetingMetadata: MeetingMetadata): SendMessageResponse {
        // Simple ISO Time validation
        Instant.parse(meetingMetadata.time)
        val metadataJson = gson.toJson(meetingMetadata)
        
        val encryptedPayload = if (isSpace) {
            val key = spaceKeys[targetId] ?: throw IllegalArgumentException("No key for space $targetId found locally")
            CryptoEngine.encryptAesGcm(key, metadataJson.toByteArray(Charsets.UTF_8)).toHex()
        } else {
            val recipientPubKeyPem = getUserPublicKeyPem(targetId)
            val key = deriveSharedKey(recipientPubKeyPem)
            CryptoEngine.encryptAesGcm(key, metadataJson.toByteArray(Charsets.UTF_8)).toHex()
        }
        
        return apiClient.sendMessage(
            senderId = userId,
            recipientId = if (isSpace) null else targetId,
            spaceId = if (isSpace) targetId else null,
            payloadType = "meeting",
            encryptedPayload = encryptedPayload
        )
    }

    fun shareFile(targetId: String, isSpace: Boolean, fileName: String, fileBytes: ByteArray): SendMessageResponse {
        // 1. Generate AES-256 file key
        val fileKey = ByteArray(32).also { secureRandom.nextBytes(it) }
        
        // 2. Encrypt file bytes
        val encryptedFileBytes = CryptoEngine.encryptAesGcm(fileKey, fileBytes)
        
        // 3. Upload encrypted bytes
        val uploadResp = apiClient.uploadFile(
            fileBytes = encryptedFileBytes,
            fileName = fileName,
            userId = userId,
            spaceId = if (isSpace) targetId else null,
            recipientId = if (isSpace) null else targetId
        )
        val fileId = uploadResp.fileId

        // 4. Resolve channel key
        val channelKey = if (isSpace) {
            spaceKeys[targetId] ?: throw IllegalArgumentException("No key for space $targetId found locally")
        } else {
            val recipientPubKeyPem = getUserPublicKeyPem(targetId)
            deriveSharedKey(recipientPubKeyPem)
        }

        // 5. Encrypt file key under channel key
        val encryptedFileKeyHex = CryptoEngine.encryptAesGcm(channelKey, fileKey).toHex()

        // 6. Encrypt metadata under channel key
        val metadata = FileMetadata(fileId, fileName, encryptedFileKeyHex)
        val metadataJson = gson.toJson(metadata)
        val encryptedPayloadHex = CryptoEngine.encryptAesGcm(channelKey, metadataJson.toByteArray(Charsets.UTF_8)).toHex()

        // 7. Send message containing metadata
        return apiClient.sendMessage(
            senderId = userId,
            recipientId = if (isSpace) null else targetId,
            spaceId = if (isSpace) targetId else null,
            payloadType = "file",
            encryptedPayload = encryptedPayloadHex
        )
    }

    fun downloadAndDecryptFile(fileId: String, encryptedFileKeyHex: String, channelKey: ByteArray): ByteArray {
        // 1. Decrypt file key
        val fileKey = CryptoEngine.decryptAesGcm(channelKey, encryptedFileKeyHex.hexToByteArray())
        
        // 2. Download from backend
        val encryptedFileBytes = apiClient.downloadFile(fileId, userId)
        
        // 3. Decrypt file bytes
        return CryptoEngine.decryptAesGcm(fileKey, encryptedFileBytes)
    }

    fun getUserDirectory(): List<User> {
        return apiClient.getUsers()
    }

    fun getSpaceMembers(spaceId: String): List<String> {
        return apiClient.getSpaceMembers(spaceId).members
    }

    fun leaveSpace(spaceId: String): LeaveSpaceResponse {
        val resp = apiClient.leaveSpace(spaceId, userId)
        spaceKeys.remove(spaceId)
        return resp
    }
}
```
