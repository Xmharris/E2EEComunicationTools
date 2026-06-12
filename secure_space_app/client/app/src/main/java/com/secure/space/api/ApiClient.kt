package com.secure.space.api

import com.google.gson.Gson
import com.google.gson.reflect.TypeToken
import com.secure.space.model.*
import okhttp3.*
import java.io.IOException
import java.util.concurrent.TimeUnit

open class ApiClient(private val baseUrl: String = "http://127.0.0.1:8089") {
    private var token: String? = null

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val original = chain.request()
            val currentToken = token
            if (currentToken != null && original.header("Authorization") == null) {
                val request = original.newBuilder()
                    .header("Authorization", "Bearer $currentToken")
                    .build()
                chain.proceed(request)
            } else {
                chain.proceed(original)
            }
        }
        .build()

    private val gson = Gson()
    private val jsonMediaType = MediaType.parse("application/json; charset=utf-8")

    private fun <T> executeRequest(request: Request, responseClass: Class<T>): T {
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val errorBody = response.body()?.string() ?: ""
                throw IOException("HTTP ${response.code()}: ${response.message()}. Body: $errorBody")
            }
            val bodyString = response.body()?.string() ?: throw IOException("Empty response body")
            return gson.fromJson(bodyString, responseClass)
        }
    }

    private fun <T> executeRequestList(request: Request, typeToken: java.lang.reflect.Type): T {
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val errorBody = response.body()?.string() ?: ""
                throw IOException("HTTP ${response.code()}: ${response.message()}. Body: $errorBody")
            }
            val bodyString = response.body()?.string() ?: throw IOException("Empty response body")
            return gson.fromJson(bodyString, typeToken)
        }
    }

    open fun resetBackend() {
        val request = Request.Builder()
            .url("$baseUrl/api/reset")
            .post(RequestBody.create(jsonMediaType, ""))
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                throw IOException("HTTP ${response.code()}: ${response.message()}")
            }
        }
    }

    open fun registerUser(requestDto: UserRegisterRequest): RegisterResponse {
        val json = gson.toJson(requestDto)
        val body = RequestBody.create(jsonMediaType, json)
        val request = Request.Builder()
            .url("$baseUrl/api/users/register")
            .post(body)
            .build()
        val response = executeRequest(request, RegisterResponse::class.java)
        this.token = response.token
        return response
    }

    open fun getUsers(): List<User> {
        val request = Request.Builder()
            .url("$baseUrl/api/users")
            .get()
            .build()
        val type = object : TypeToken<List<User>>() {}.type
        return executeRequestList(request, type)
    }

    open fun createSpace(requestDto: SpaceCreateRequest): SpaceCreateResponse {
        val json = gson.toJson(requestDto)
        val body = RequestBody.create(jsonMediaType, json)
        val request = Request.Builder()
            .url("$baseUrl/api/spaces/create")
            .post(body)
            .build()
        return executeRequest(request, SpaceCreateResponse::class.java)
    }

    open fun addMember(requestDto: AddMemberRequest): AddMemberResponse {
        val json = gson.toJson(requestDto)
        val body = RequestBody.create(jsonMediaType, json)
        val request = Request.Builder()
            .url("$baseUrl/api/spaces/add_member")
            .post(body)
            .build()
        return executeRequest(request, AddMemberResponse::class.java)
    }

    open fun leaveSpace(requestDto: LeaveSpaceRequest): LeaveSpaceResponse {
        val json = gson.toJson(requestDto)
        val body = RequestBody.create(jsonMediaType, json)
        val request = Request.Builder()
            .url("$baseUrl/api/spaces/leave")
            .post(body)
            .build()
        return executeRequest(request, LeaveSpaceResponse::class.java)
    }

    open fun getSpaceKey(spaceId: String, userId: String): SpaceKeyResponse {
        val url = HttpUrl.parse("$baseUrl/api/spaces/$spaceId/key")!!.newBuilder()
            .addQueryParameter("user_id", userId)
            .build()
        val request = Request.Builder()
            .url(url)
            .get()
            .build()
        return executeRequest(request, SpaceKeyResponse::class.java)
    }

    open fun getSpaceMembers(spaceId: String): SpaceMembersResponse {
        val request = Request.Builder()
            .url("$baseUrl/api/spaces/$spaceId/members")
            .get()
            .build()
        return executeRequest(request, SpaceMembersResponse::class.java)
    }

    open fun sendMessage(requestDto: MessageSendRequest): SendMessageResponse {
        val json = gson.toJson(requestDto)
        val body = RequestBody.create(jsonMediaType, json)
        val request = Request.Builder()
            .url("$baseUrl/api/messages/send")
            .post(body)
            .build()
        return executeRequest(request, SendMessageResponse::class.java)
    }

    open fun getMessages(userId: String, spaceId: String? = null): List<Message> {
        val urlBuilder = HttpUrl.parse("$baseUrl/api/messages")!!.newBuilder()
            .addQueryParameter("user_id", userId)
        if (spaceId != null) {
            urlBuilder.addQueryParameter("space_id", spaceId)
        }
        val request = Request.Builder()
            .url(urlBuilder.build())
            .get()
            .build()
        val type = object : TypeToken<List<Message>>() {}.type
        return executeRequestList(request, type)
    }

    open fun uploadFile(
        fileBytes: ByteArray,
        fileName: String,
        userId: String? = null,
        spaceId: String? = null,
        recipientId: String? = null
    ): UploadFileResponse {
        val urlBuilder = HttpUrl.parse("$baseUrl/api/files/upload")!!.newBuilder()
        if (userId != null) urlBuilder.addQueryParameter("user_id", userId)
        if (spaceId != null) urlBuilder.addQueryParameter("space_id", spaceId)
        if (recipientId != null) urlBuilder.addQueryParameter("recipient_id", recipientId)

        val fileBody = RequestBody.create(MediaType.parse("application/octet-stream"), fileBytes)
        val requestBody = MultipartBody.Builder()
            .setType(MultipartBody.FORM)
            .addFormDataPart("file", fileName, fileBody)
            .build()

        val request = Request.Builder()
            .url(urlBuilder.build())
            .post(requestBody)
            .build()
        return executeRequest(request, UploadFileResponse::class.java)
    }

    open fun downloadFile(fileId: String, userId: String? = null): ByteArray {
        val urlBuilder = HttpUrl.parse("$baseUrl/api/files/download/$fileId")!!.newBuilder()
        if (userId != null) {
            urlBuilder.addQueryParameter("user_id", userId)
        }
        val request = Request.Builder()
            .url(urlBuilder.build())
            .get()
            .build()
        client.newCall(request).execute().use { response ->
            if (!response.isSuccessful) {
                val errorBody = response.body()?.string() ?: ""
                throw IOException("HTTP ${response.code()}: ${response.message()}. Body: $errorBody")
            }
            return response.body()?.bytes() ?: throw IOException("Empty response body")
        }
    }
}
