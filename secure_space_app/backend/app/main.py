import uuid
import re
import hashlib
import os
import sqlite3
from typing import List, Dict, Optional
import datetime
from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Response, Depends, Header, Request
from pydantic import BaseModel
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

app = FastAPI(title="Secure Space Real Backend")

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "secure_space.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        public_key TEXT NOT NULL,
        token TEXT NOT NULL DEFAULT ''
    )
    """)
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN token TEXT NOT NULL DEFAULT ''")
    except Exception:
        pass
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS spaces (
        space_id TEXT PRIMARY KEY,
        creator_id TEXT NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS space_keys (
        space_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        encrypted_key TEXT NOT NULL,
        PRIMARY KEY (space_id, user_id)
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sender_id TEXT NOT NULL,
        recipient_id TEXT,
        space_id TEXT,
        payload_type TEXT NOT NULL,
        encrypted_payload TEXT NOT NULL
    )
    """)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS files (
        file_id TEXT PRIMARY KEY,
        file_bytes BLOB NOT NULL,
        user_id TEXT,
        space_id TEXT,
        recipient_id TEXT
    )
    """)
    conn.commit()
    conn.close()

# Initialize database tables on startup
if os.path.exists(DB_PATH):
    try:
        os.remove(DB_PATH)
    except Exception:
        pass
init_db()

def get_current_user(
    authorization: Optional[str] = Header(None),
    token: Optional[str] = Query(None)
) -> str:
    current_token = None
    if authorization:
        if authorization.startswith("Bearer "):
            current_token = authorization[len("Bearer "):]
        else:
            current_token = authorization
    elif token:
        current_token = token
        
    if not current_token:
        raise HTTPException(status_code=401, detail="Unauthorized: Missing token")
        
    hashed_token = hashlib.sha256(current_token.encode('utf-8')).hexdigest()
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE token = ?", (hashed_token,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid token")
        
    return row["user_id"]


# Pydantic models for request bodies
class UserRegisterRequest(BaseModel):
    user_id: str
    public_key: str


class LoginChallengeRequest(BaseModel):
    user_id: str


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
def reset_backend(request: Request):
    client_host = request.client.host if request.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost", "testclient", "testserver"):
        raise HTTPException(status_code=403, detail="Reset only allowed in local test environment")
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users")
    cursor.execute("DELETE FROM spaces")
    cursor.execute("DELETE FROM space_keys")
    cursor.execute("DELETE FROM messages")
    cursor.execute("DELETE FROM files")
    conn.commit()
    conn.close()
    return {"status": "reset"}


@app.post("/api/users/register")
def register_user(request: UserRegisterRequest):
    username = request.user_id
    if not username or not request.public_key:
        raise HTTPException(status_code=400, detail="Invalid user_id or public_key")
    
    # 1. Empty username check
    if not username.strip():
        raise HTTPException(status_code=400, detail="Username cannot be empty")
        
    # 2. Duplicate username check
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (username,))
    row = cursor.fetchone()
    if row:
        conn.close()
        raise HTTPException(status_code=400, detail="Username already registered")
        
    # 3. Validation for extremely long username
    if len(username) > 100:
        conn.close()
        raise HTTPException(status_code=400, detail="Username too long")
        
    # 4. Special characters validation
    if not re.match(r"^[a-zA-Z0-9_-]+$", username):
        conn.close()
        raise HTTPException(status_code=400, detail="Username contains invalid characters")
        
    # 5. Invalid PEM public key format check
    try:
        serialization.load_pem_public_key(request.public_key.encode('utf-8'))
    except Exception:
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid public key format")
        
    # 6. Duplicate public key check
    cursor.execute("SELECT 1 FROM users WHERE public_key = ?", (request.public_key,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Public key already registered")
        
    # Generate secure token
    token = str(uuid.uuid4())
    hashed_token = hashlib.sha256(token.encode('utf-8')).hexdigest()
        
    # Insert user
    cursor.execute("INSERT INTO users (user_id, public_key, token) VALUES (?, ?, ?)", (username, request.public_key, hashed_token))
    conn.commit()
    conn.close()
    return {"status": "registered", "user_id": username, "token": token}


@app.post("/api/users/login/challenge")
def login_challenge(request: LoginChallengeRequest):
    username = request.user_id
    if not username:
        raise HTTPException(status_code=400, detail="Invalid user_id")
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT public_key FROM users WHERE user_id = ?", (username,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
        
    public_key_pem = row["public_key"]
    
    try:
        user_pubkey = serialization.load_pem_public_key(public_key_pem.encode('utf-8'))
        if not isinstance(user_pubkey, ec.EllipticCurvePublicKey):
            conn.close()
            raise HTTPException(status_code=400, detail="Unsupported key type. Only ECDH is supported for login.")
            
        # Generate ephemeral keypair of the same curve (expected SECP256R1 / P-256)
        ephemeral_private_key = ec.generate_private_key(user_pubkey.curve)
        ephemeral_public_key = ephemeral_private_key.public_key()
        
        ephemeral_public_key_pem = ephemeral_public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        # Derive shared secret
        shared_key_raw = ephemeral_private_key.exchange(ec.ECDH(), user_pubkey)
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b'secure-space-e2ee-key-agreement'
        ).derive(shared_key_raw)
        
        # Generate new token
        new_token = str(uuid.uuid4())
        hashed_token = hashlib.sha256(new_token.encode('utf-8')).hexdigest()
        
        # Encrypt token (AES-GCM)
        aesgcm = AESGCM(derived_key)
        iv = os.urandom(12)
        encrypted_token_bytes = iv + aesgcm.encrypt(iv, new_token.encode('utf-8'), None)
        encrypted_token_hex = encrypted_token_bytes.hex()
        
        # Update user token in DB
        cursor.execute("UPDATE users SET token = ? WHERE user_id = ?", (hashed_token, username))
        conn.commit()
        conn.close()
        
        return {
            "ephemeral_public_key": ephemeral_public_key_pem,
            "encrypted_token": encrypted_token_hex
        }
    except Exception as e:
        conn.close()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/users")
def get_users(current_user: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, public_key FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [{"user_id": row["user_id"], "public_key": row["public_key"]} for row in rows]


@app.get("/api/spaces")
def get_user_spaces(current_user: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT space_id FROM space_keys WHERE user_id = ?", (current_user,))
    rows = cursor.fetchall()
    conn.close()
    return [{"space_id": row["space_id"]} for row in rows]


@app.post("/api/spaces/create")
def create_space(request: SpaceCreateRequest, current_user: str = Depends(get_current_user)):
    space_id = request.space_id
    creator_id = request.creator_id
    if not space_id or not creator_id:
        raise HTTPException(status_code=400, detail="Invalid space_id or creator_id")
    if not space_id.strip():
        raise HTTPException(status_code=400, detail="Space ID cannot be empty")
        
    if current_user != creator_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot create space for another user")
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if space already exists
    cursor.execute("SELECT 1 FROM spaces WHERE space_id = ?", (space_id,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Space already exists")
        
    # Check if creator exists
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (creator_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Creator not registered")
        
    cursor.execute("INSERT INTO spaces (space_id, creator_id) VALUES (?, ?)", (space_id, creator_id))
    conn.commit()
    conn.close()
    return {"status": "created", "space_id": space_id}


@app.post("/api/spaces/add_member")
def add_member(request: AddMemberRequest, current_user: str = Depends(get_current_user)):
    space_id = request.space_id
    user_id = request.user_id
    encrypted_key = request.encrypted_key
    
    if not space_id or not user_id or not encrypted_key:
        raise HTTPException(status_code=400, detail="Missing required parameters")
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if space exists and get creator
    cursor.execute("SELECT creator_id FROM spaces WHERE space_id = ?", (space_id,))
    space_row = cursor.fetchone()
    if not space_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Space not found")
    creator_id = space_row["creator_id"]
        
    # Check authorization: caller must be creator or member
    cursor.execute("SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?", (space_id, current_user))
    is_member = cursor.fetchone() is not None
    if current_user != creator_id and not is_member:
        conn.close()
        raise HTTPException(status_code=403, detail="Forbidden: Caller is not creator or member of space")
        
    # Check if user to be added exists
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="User not found")
        
    # Check if user is already a member
    cursor.execute("SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?", (space_id, user_id))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="User already member of space")
        
    # Store space key for member
    cursor.execute(
        "INSERT INTO space_keys (space_id, user_id, encrypted_key) VALUES (?, ?, ?)",
        (space_id, user_id, encrypted_key)
    )
    conn.commit()
    conn.close()
    return {
        "status": "added",
        "space_id": space_id,
        "user_id": user_id
    }


@app.post("/api/spaces/leave")
def leave_space(request: LeaveSpaceRequest, current_user: str = Depends(get_current_user)):
    space_id = request.space_id
    user_id = request.user_id
    if not space_id or not user_id:
        raise HTTPException(status_code=400, detail="Missing required parameters")
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if space exists and get creator
    cursor.execute("SELECT creator_id FROM spaces WHERE space_id = ?", (space_id,))
    space_row = cursor.fetchone()
    if not space_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Space not found")
    creator_id = space_row["creator_id"]
    
    # Caller must be user leaving or creator
    if current_user != user_id and current_user != creator_id:
        conn.close()
        raise HTTPException(status_code=403, detail="Forbidden: Caller cannot force another user to leave")
        
    # Check membership and delete
    cursor.execute("SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?", (space_id, user_id))
    if cursor.fetchone():
        cursor.execute("DELETE FROM space_keys WHERE space_id = ? AND user_id = ?", (space_id, user_id))
        conn.commit()
        conn.close()
        return {"status": "left", "space_id": space_id, "user_id": user_id}
    else:
        conn.close()
        raise HTTPException(status_code=404, detail="User is not a member of the space")


@app.get("/api/spaces/{space_id}/key")
def get_space_key(space_id: str, user_id: str = Query(...), current_user: str = Depends(get_current_user)):
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot retrieve key for another user")
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Check space existence
    cursor.execute("SELECT creator_id FROM spaces WHERE space_id = ?", (space_id,))
    space_row = cursor.fetchone()
    if not space_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Space not found")
    creator_id = space_row["creator_id"]
        
    # Check user key
    cursor.execute(
        "SELECT encrypted_key FROM space_keys WHERE space_id = ? AND user_id = ?",
        (space_id, user_id)
    )
    key_row = cursor.fetchone()
    if not key_row:
        conn.close()
        raise HTTPException(
            status_code=404, 
            detail=f"Key not found for space {space_id} and user {user_id}"
        )
        
    creator_id = space_row["creator_id"]
    encrypted_key = key_row["encrypted_key"]
    conn.close()
    return {
        "space_id": space_id,
        "user_id": user_id,
        "encrypted_key": encrypted_key,
        "creator_id": creator_id
    }


@app.get("/api/spaces/{space_id}/members")
def get_space_members(space_id: str, current_user: str = Depends(get_current_user)):
    conn = get_db()
    cursor = conn.cursor()
    
    # Check space existence
    cursor.execute("SELECT creator_id FROM spaces WHERE space_id = ?", (space_id,))
    space_row = cursor.fetchone()
    if not space_row:
        conn.close()
        raise HTTPException(status_code=404, detail="Space not found")
    creator_id = space_row["creator_id"]
    
    # Check authorization: caller must be creator or member
    cursor.execute("SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?", (space_id, current_user))
    is_member = cursor.fetchone() is not None
    
    if current_user != creator_id and not is_member:
        conn.close()
        raise HTTPException(status_code=403, detail="Forbidden: Caller is not a member of the space")
        
    cursor.execute("SELECT user_id FROM space_keys WHERE space_id = ?", (space_id,))
    rows = cursor.fetchall()
    conn.close()
    members = [row["user_id"] for row in rows]
    return {"space_id": space_id, "members": members}


@app.post("/api/messages/send")
def send_message(request: MessageSendRequest, current_user: str = Depends(get_current_user)):
    if current_user != request.sender_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot send message as another user")
    if not request.sender_id or not request.payload_type or not request.encrypted_payload:
        raise HTTPException(status_code=400, detail="Missing required parameters")
    if not request.space_id and not request.recipient_id:
        raise HTTPException(status_code=400, detail="Message must have a space_id or recipient_id")
        
    # Verify encrypted_payload is not empty
    if not request.encrypted_payload.strip():
        raise HTTPException(status_code=400, detail="Encrypted payload cannot be empty")
        
    conn = get_db()
    cursor = conn.cursor()
    
    # Verify sender exists
    cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (request.sender_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=401, detail="Sender not registered")
        
    if request.space_id:
        # Check space existence
        cursor.execute("SELECT creator_id FROM spaces WHERE space_id = ?", (request.space_id,))
        space_row = cursor.fetchone()
        if not space_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Space not found")
        creator_id = space_row["creator_id"]
        # Check membership
        cursor.execute(
            "SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?",
            (request.space_id, request.sender_id)
        )
        is_member = cursor.fetchone() is not None
        if request.sender_id != creator_id and not is_member:
            conn.close()
            raise HTTPException(status_code=403, detail="Sender is not a member of the space")
    else:
        # DM message
        cursor.execute("SELECT 1 FROM users WHERE user_id = ?", (request.recipient_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Recipient not found")
        if request.sender_id == request.recipient_id:
            conn.close()
            raise HTTPException(status_code=400, detail="Cannot send DM to self")
            
    # Replay attack prevention
    cursor.execute("SELECT 1 FROM messages WHERE encrypted_payload = ?", (request.encrypted_payload,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Replay attack detected: Duplicate message payload")

    # Insert message
    cursor.execute(
        """
        INSERT INTO messages (sender_id, recipient_id, space_id, payload_type, encrypted_payload)
        VALUES (?, ?, ?, ?, ?)
        """,
        (request.sender_id, request.recipient_id, request.space_id, request.payload_type, request.encrypted_payload)
    )
    msg_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return {"status": "sent", "message_id": msg_id}


@app.get("/api/messages")
def get_messages(
    user_id: Optional[str] = Query(None), 
    space_id: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user)
):
    if not user_id:
        raise HTTPException(status_code=403, detail="Forbidden: user_id is required")
        
    if current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot retrieve messages for another user")
        
    conn = get_db()
    cursor = conn.cursor()
    
    if space_id is not None:
        # Check space existence
        cursor.execute("SELECT creator_id FROM spaces WHERE space_id = ?", (space_id,))
        space_row = cursor.fetchone()
        if not space_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Space not found")
        creator_id = space_row["creator_id"]
            
        # Check space membership
        cursor.execute("SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?", (space_id, user_id))
        is_member = cursor.fetchone() is not None
        if user_id != creator_id and not is_member:
            conn.close()
            raise HTTPException(status_code=403, detail="Forbidden: User is not a member of the space")
            
        cursor.execute(
            """
            SELECT id, sender_id, recipient_id, space_id, payload_type, encrypted_payload
            FROM messages WHERE space_id = ?
            """,
            (space_id,)
        )
    else:
        # DM messages
        cursor.execute(
            """
            SELECT id, sender_id, recipient_id, space_id, payload_type, encrypted_payload
            FROM messages WHERE space_id IS NULL AND (sender_id = ? OR recipient_id = ?)
            """,
            (user_id, user_id)
        )
        
    rows = cursor.fetchall()
    conn.close()
    
    return [
        {
            "id": row["id"],
            "sender_id": row["sender_id"],
            "recipient_id": row["recipient_id"],
            "space_id": row["space_id"],
            "payload_type": row["payload_type"],
            "encrypted_payload": row["encrypted_payload"]
        }
        for row in rows
    ]


@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    recipient_id: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user)
):
    if user_id and current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot upload file as another user")
        
    if space_id:
        conn = get_db()
        cursor = conn.cursor()
        # Check space existence
        cursor.execute("SELECT creator_id FROM spaces WHERE space_id = ?", (space_id,))
        space_row = cursor.fetchone()
        if not space_row:
            conn.close()
            raise HTTPException(status_code=404, detail="Space not found")
        creator_id = space_row["creator_id"]
        
        cursor.execute("SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?", (space_id, current_user))
        is_member = cursor.fetchone() is not None
        conn.close()
        if current_user != creator_id and not is_member:
            raise HTTPException(status_code=403, detail="Forbidden: User is not a member of the space")
            
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="Cannot upload empty file")
        
    file_id = str(uuid.uuid4())
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO files (file_id, file_bytes, user_id, space_id, recipient_id) VALUES (?, ?, ?, ?, ?)",
        (file_id, sqlite3.Binary(file_bytes), user_id, space_id, recipient_id)
    )
    conn.commit()
    conn.close()
    
    return {"file_id": file_id}


@app.get("/api/files/download/{file_id}")
def download_file(
    file_id: str, 
    user_id: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user)
):
    if user_id and current_user != user_id:
        raise HTTPException(status_code=403, detail="Forbidden: Cannot download file for another user")
        
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT file_bytes, user_id, space_id, recipient_id FROM files WHERE file_id = ?", (file_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail="File not found")
        
    uploader = row["user_id"]
    space_id = row["space_id"]
    recipient_id = row["recipient_id"]
    
    if uploader is None and space_id is None and recipient_id is None:
        raise HTTPException(status_code=403, detail="Forbidden: Anonymous file download is not allowed")
        
    eff_user_id = user_id if user_id else current_user
    
    if uploader is not None or space_id is not None or recipient_id is not None:
        # 1. Allow access if eff_user_id == uploader
        if eff_user_id == uploader:
            pass
        # 2. If space_id is present, query space_keys to verify user_id membership
        elif space_id is not None:
            conn = get_db()
            cursor = conn.cursor()
            # Also allow space creator
            cursor.execute("SELECT creator_id FROM spaces WHERE space_id = ?", (space_id,))
            space_row = cursor.fetchone()
            creator_id = space_row["creator_id"] if space_row else None
            
            cursor.execute("SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?", (space_id, eff_user_id))
            member_row = cursor.fetchone()
            conn.close()
            if eff_user_id != creator_id and not member_row:
                raise HTTPException(status_code=403, detail="Forbidden: User is not a member of the space")
        # 3. If recipient_id is present, check if eff_user_id == recipient_id or eff_user_id == uploader
        elif recipient_id is not None:
            if eff_user_id != recipient_id and eff_user_id != uploader:
                raise HTTPException(status_code=403, detail="Forbidden: User is not the recipient or uploader")
        # 4. Otherwise, eff_user_id must be the owner (uploader)
        else:
            if eff_user_id != uploader:
                raise HTTPException(status_code=403, detail="Forbidden: User is not the uploader")
            
    return Response(content=row["file_bytes"], media_type="application/octet-stream")

import sqlite3
import os

@app.get("/api/external-meetings")
def get_external_meetings(location: str = Query(...), type: str = Query("All"), current_user: str = Depends(get_current_user)):
    db_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../na_meetings.db"))
    
    if not os.path.exists(db_path):
        return []
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT id, meeting_name, day, time, address, source_url FROM meetings")
        rows = cursor.fetchall()
        conn.close()
        
        meetings = []
        for row in rows:
            meetings.append({
                "id": f"ext-{row[0]}",
                "title": row[1],
                "type": "NA",
                "time": f"Upcoming {row[2]} at {row[3]}",
                "location": row[4],
                "description": f"Source: {row[5]}"
            })
            
        return meetings
    except Exception as e:
        print(f"Database query failed: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve meetings")
