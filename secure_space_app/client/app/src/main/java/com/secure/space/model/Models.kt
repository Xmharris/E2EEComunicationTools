package com.secure.space.model

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
    @SerializedName("user_id") val userId: String,
    @SerializedName("token") val token: String? = null
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
    @SerializedName("recipient_id") val recipientId: String? = null,
    @SerializedName("space_id") val spaceId: String? = null,
    @SerializedName("payload_type") val payloadType: String,
    @SerializedName("encrypted_payload") val encryptedPayload: String
)

data class UploadFileResponse(
    @SerializedName("file_id") val fileId: String
)

data class MeetingMetadata(
    @SerializedName("title") val title: String,
    @SerializedName("time") val time: String,
    @SerializedName("location") val location: String,
    @SerializedName("description") val description: String? = null
)

data class FileMetadata(
    @SerializedName("file_id") val fileId: String,
    @SerializedName("file_name") val fileName: String,
    @SerializedName("encrypted_file_key") val encryptedFileKey: String
)
