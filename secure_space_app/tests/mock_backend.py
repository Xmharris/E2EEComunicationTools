import uuid
import re
from typing import List, Dict, Optional
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Response
from pydantic import BaseModel
from cryptography.hazmat.primitives import serialization

app = FastAPI(title="Secure Space Mock Backend")

# In-memory database
# User schema: {user_id: public_key_pem}
users_db: Dict[str, str] = {}

# Space schema: {space_id: creator_id}
spaces_db: Dict[str, str] = {}

# Space keys: {(space_id, user_id): encrypted_key_hex}
space_keys_db: Dict[tuple, str] = {}

# Messages: List of dicts representing messages
messages_db: List[dict] = []

# Files: {file_id: bytes}
files_db: Dict[str, bytes] = {}

# File Metadata: {file_id: {"user_id": str, "space_id": Optional[str], "recipient_id": Optional[str]}}
files_metadata_db: Dict[str, dict] = {}


# Pydantic models for request bodies
class UserRegisterRequest(BaseModel):
    user_id: str
    public_key: str


class SpaceCreateRequest(BaseModel):
    space_id: str
    creator_id: str


class AddMemberRequest(BaseModel):
    space_id: str
    user_id: str
    encrypted_key: str


class LeaveSpaceRequest(BaseModel):
    space_id: str
    user_id: str


class MessageSendRequest(BaseModel):
    sender_id: str
    recipient_id: Optional[str] = None
    space_id: Optional[str] = None
    payload_type: str  # "text", "meeting", "file"
    encrypted_payload: str  # Hex or Base64 encoded encrypted payload


@app.post("/api/reset")
def reset_backend():
    users_db.clear()
    spaces_db.clear()
    space_keys_db.clear()
    messages_db.clear()
    files_db.clear()
    files_metadata_db.clear()
    return {"status": "reset"}


@app.post("/api/users/register")
def register_user(request: UserRegisterRequest):
    # Enforce basic validations
    username = request.user_id
    if not username or not request.public_key:
        raise HTTPException(status_code=400, detail="Invalid user_id or public_key")
    
    # 1. Empty username check
    if not username.strip():
        raise HTTPException(status_code=400, detail="Username cannot be empty")
        
    # 2. Duplicate username check
    if username in users_db:
        raise HTTPException(status_code=400, detail="Username already registered")
        
    # 3. Validation for extremely long username
    if len(username) > 100:
        raise HTTPException(status_code=400, detail="Username too long")
        
    # 4. Special characters validation
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        raise HTTPException(status_code=400, detail="Username contains invalid characters")
        
    # 5. Invalid PEM public key format check
    try:
        serialization.load_pem_public_key(request.public_key.encode('utf-8'))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid public key format")
        
    users_db[username] = request.public_key
    return {"status": "registered", "user_id": username}


@app.get("/api/users")
def get_users():
    return [{"user_id": uid, "public_key": pk} for uid, pk in users_db.items()]


@app.post("/api/spaces/create")
def create_space(request: SpaceCreateRequest):
    space_id = request.space_id
    creator_id = request.creator_id
    if not space_id or not creator_id:
        raise HTTPException(status_code=400, detail="Invalid space_id or creator_id")
    if not space_id.strip():
        raise HTTPException(status_code=400, detail="Space ID cannot be empty")
    if space_id in spaces_db:
        raise HTTPException(status_code=400, detail="Space already exists")
    if creator_id not in users_db:
        raise HTTPException(status_code=404, detail="Creator not registered")
        
    spaces_db[space_id] = creator_id
    return {"status": "created", "space_id": space_id}


@app.post("/api/spaces/add_member")
def add_member(request: AddMemberRequest):
    space_id = request.space_id
    user_id = request.user_id
    encrypted_key = request.encrypted_key
    
    if not space_id or not user_id or not encrypted_key:
        raise HTTPException(status_code=400, detail="Missing required parameters")
        
    if space_id not in spaces_db:
        raise HTTPException(status_code=404, detail="Space not found")
        
    if user_id not in users_db:
        raise HTTPException(status_code=404, detail="User not found")
        
    if (space_id, user_id) in space_keys_db:
        raise HTTPException(status_code=400, detail="User already member of space")
        
    # Store the encrypted key for this specific space member
    space_keys_db[(space_id, user_id)] = encrypted_key
    return {
        "status": "added",
        "space_id": space_id,
        "user_id": user_id
    }


@app.post("/api/spaces/leave")
def leave_space(request: LeaveSpaceRequest):
    space_id = request.space_id
    user_id = request.user_id
    if not space_id or not user_id:
        raise HTTPException(status_code=400, detail="Missing required parameters")
    if space_id not in spaces_db:
        raise HTTPException(status_code=404, detail="Space not found")
    
    key = (space_id, user_id)
    if key in space_keys_db:
        del space_keys_db[key]
        return {"status": "left", "space_id": space_id, "user_id": user_id}
    else:
        raise HTTPException(status_code=404, detail="User is not a member of the space")


@app.get("/api/spaces/{space_id}/key")
def get_space_key(space_id: str, user_id: str = Query(...)):
    if space_id not in spaces_db:
        raise HTTPException(status_code=404, detail="Space not found")
    key = space_keys_db.get((space_id, user_id))
    if key is None:
        raise HTTPException(
            status_code=404, 
            detail=f"Key not found for space {space_id} and user {user_id}"
        )
    creator_id = spaces_db.get(space_id)
    return {
        "space_id": space_id,
        "user_id": user_id,
        "encrypted_key": key,
        "creator_id": creator_id
    }


@app.get("/api/spaces/{space_id}/members")
def get_space_members(space_id: str):
    if space_id not in spaces_db:
        raise HTTPException(status_code=404, detail="Space not found")
    members = [u_id for (s_id, u_id) in space_keys_db.keys() if s_id == space_id]
    return {"space_id": space_id, "members": members}


@app.post("/api/messages/send")
def send_message(request: MessageSendRequest):
    if not request.sender_id or not request.payload_type or not request.encrypted_payload:
        raise HTTPException(status_code=400, detail="Missing required parameters")
    if not request.space_id and not request.recipient_id:
        raise HTTPException(status_code=400, detail="Message must have a space_id or recipient_id")
        
    if request.sender_id not in users_db:
        raise HTTPException(status_code=401, detail="Sender not registered")
        
    if request.space_id:
        # Space message
        if request.space_id not in spaces_db:
            raise HTTPException(status_code=404, detail="Space not found")
        # Check membership
        if (request.space_id, request.sender_id) not in space_keys_db:
            raise HTTPException(status_code=403, detail="Sender is not a member of the space")
    else:
        # DM message
        if request.recipient_id not in users_db:
            raise HTTPException(status_code=404, detail="Recipient not found")
        if request.sender_id == request.recipient_id:
            raise HTTPException(status_code=400, detail="Cannot send DM to self")
            
    # Verify encrypted_payload is not an empty string
    if not request.encrypted_payload.strip():
        raise HTTPException(status_code=400, detail="Encrypted payload cannot be empty")
        
    msg_id = len(messages_db) + 1
    msg = {
        "id": msg_id,
        "sender_id": request.sender_id,
        "recipient_id": request.recipient_id,
        "space_id": request.space_id,
        "payload_type": request.payload_type,
        "encrypted_payload": request.encrypted_payload
    }
    messages_db.append(msg)
    return {"status": "sent", "message_id": msg_id}


@app.get("/api/messages")
def get_messages(
    user_id: Optional[str] = Query(None), 
    space_id: Optional[str] = Query(None)
):
    # Enforce access control: user_id is required
    if not user_id:
        raise HTTPException(status_code=403, detail="Forbidden: user_id is required")

    filtered_messages = []
    
    if space_id is not None:
        if space_id not in spaces_db:
            raise HTTPException(status_code=404, detail="Space not found")
        # Verify that the requesting user_id is a member of the space
        if (space_id, user_id) not in space_keys_db:
            raise HTTPException(status_code=403, detail="Forbidden: User is not a member of the space")
            
        for msg in messages_db:
            if msg.get("space_id") == space_id:
                filtered_messages.append(msg)
    else:
        # DM messages: verify that requesting user is either the sender or recipient
        for msg in messages_db:
            if msg.get("space_id") is None:
                if msg.get("sender_id") == user_id or msg.get("recipient_id") == user_id:
                    filtered_messages.append(msg)
                    
    return filtered_messages


@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    recipient_id: Optional[str] = Query(None)
):
    file_bytes = await file.read()
    # Check for empty file
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Cannot upload empty file")
    
    file_id = str(uuid.uuid4())
    files_db[file_id] = file_bytes
    
    # Store metadata if provided
    meta = {}
    if user_id:
        meta["user_id"] = user_id
    if space_id:
        meta["space_id"] = space_id
    if recipient_id:
        meta["recipient_id"] = recipient_id
    files_metadata_db[file_id] = meta
    
    return {"file_id": file_id}


@app.get("/api/files/download/{file_id}")
def download_file(file_id: str, user_id: Optional[str] = Query(None)):
    file_bytes = files_db.get(file_id)
    if file_bytes is None:
        raise HTTPException(status_code=404, detail="File not found")
        
    meta = files_metadata_db.get(file_id)
    if meta:
        # Enforce access control
        if not user_id:
            raise HTTPException(status_code=403, detail="Forbidden: user_id is required")
            
        uploader = meta.get("user_id")
        space_id = meta.get("space_id")
        recipient_id = meta.get("recipient_id")
        
        # Checking:
        # 1. Is user the uploader/owner?
        if user_id == uploader:
            pass # authorized
        # 2. Is it shared in a space?
        elif space_id is not None:
            # Check space membership
            if (space_id, user_id) not in space_keys_db:
                raise HTTPException(status_code=403, detail="Forbidden: Not a member of the space")
        # 3. Is it a DM?
        elif recipient_id is not None:
            if user_id != recipient_id and user_id != uploader:
                raise HTTPException(status_code=403, detail="Forbidden: Not authorized to access this file")
        # 4. Otherwise, user_id must be the owner
        else:
            if user_id != uploader:
                raise HTTPException(status_code=403, detail="Forbidden: Not authorized to access this file")
                
    return Response(content=file_bytes, media_type="application/octet-stream")
