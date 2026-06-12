import os
import json
import requests
from datetime import datetime
from typing import List, Dict, Optional
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

class ClientSim:
    def __init__(self, user_id: str, backend_url: str):
        self.user_id = user_id
        self.backend_url = backend_url
        
        # Generate X25519 private key
        self.private_key = x25519.X25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        
        # Export public key in PEM format
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        # Local space key store: {space_id: space_key_bytes}
        self.space_keys: Dict[str, bytes] = {}
        self.token = None
        self.session = requests.Session()

    def register(self) -> dict:
        """Register the user with the backend."""
        resp = self.session.post(
            f"{self.backend_url}/api/users/register",
            json={
                "user_id": self.user_id,
                "public_key": self.public_key_pem
            }
        )
        resp.raise_for_status()
        data = resp.json()
        if "token" in data:
            self.token = data["token"]
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})
        return data

    def get_public_key_pem(self) -> str:
        return self.public_key_pem

    def _get_user_public_key(self, peer_id: str) -> str:
        """Resolve user public key from /api/users."""
        resp = self.session.get(f"{self.backend_url}/api/users")
        resp.raise_for_status()
        users = resp.json()
        for u in users:
            if u["user_id"] == peer_id:
                return u["public_key"]
        raise ValueError(f"Public key for user '{peer_id}' not found on backend.")

    def _derive_shared_key(self, peer_public_key_pem: str) -> bytes:
        """ECDH key agreement + HKDF (SHA-256) to derive a 256-bit symmetric key."""
        peer_pubkey = serialization.load_pem_public_key(peer_public_key_pem.encode('utf-8'))
        shared_key_raw = self.private_key.exchange(peer_pubkey)
        
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b'secure-space-e2ee-key-agreement'
        ).derive(shared_key_raw)
        
        return derived_key

    @staticmethod
    def encrypt_aes_gcm(key: bytes, plaintext: bytes) -> str:
        """AES-GCM (256-bit) encryption returning a hex string containing IV + ciphertext."""
        aesgcm = AESGCM(key)
        iv = os.urandom(12)
        ciphertext = aesgcm.encrypt(iv, plaintext, None)
        return (iv + ciphertext).hex()

    @staticmethod
    def decrypt_aes_gcm(key: bytes, ciphertext_hex: str) -> bytes:
        """AES-GCM (256-bit) decryption of a hex string containing IV + ciphertext."""
        data = bytes.fromhex(ciphertext_hex)
        if len(data) < 12:
            raise ValueError("Ciphertext too short")
        iv = data[:12]
        ciphertext = data[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(iv, ciphertext, None)

    @staticmethod
    def encrypt_aes_gcm_bytes(key: bytes, plaintext: bytes) -> bytes:
        """AES-GCM (256-bit) encryption returning raw bytes (IV + ciphertext)."""
        aesgcm = AESGCM(key)
        iv = os.urandom(12)
        return iv + aesgcm.encrypt(iv, plaintext, None)

    @staticmethod
    def decrypt_aes_gcm_bytes(key: bytes, ciphertext_bytes: bytes) -> bytes:
        """AES-GCM (256-bit) decryption of raw bytes (IV + ciphertext)."""
        if len(ciphertext_bytes) < 12:
            raise ValueError("Ciphertext too short")
        iv = ciphertext_bytes[:12]
        ciphertext = ciphertext_bytes[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(iv, ciphertext, None)

    def create_space(self, space_id: str) -> dict:
        """Creator generates random space key (AES-256) and creates space on backend."""
        # Generate AES-256 space key
        space_key = AESGCM.generate_key(bit_length=256)
        self.space_keys[space_id] = space_key
        
        # Create space
        resp = self.session.post(
            f"{self.backend_url}/api/spaces/create",
            json={
                "space_id": space_id,
                "creator_id": self.user_id
            }
        )
        resp.raise_for_status()
        
        # Add creator to the space keys database
        self.add_member_to_space(space_id, self.user_id)
        
        return resp.json()

    def add_member_to_space(self, space_id: str, member_id: str) -> dict:
        """Encrypts space key with ECDH shared key for member, uploads it."""
        space_key = self.space_keys.get(space_id)
        if not space_key:
            raise ValueError(f"Space key for '{space_id}' not found locally")
            
        # Get member public key
        member_pubkey_pem = self._get_user_public_key(member_id)
        
        # Derive shared key between creator and member
        shared_key = self._derive_shared_key(member_pubkey_pem)
        
        # Encrypt the space key using the shared key
        encrypted_key_hex = self.encrypt_aes_gcm(shared_key, space_key)
        
        # Upload key
        resp = self.session.post(
            f"{self.backend_url}/api/spaces/add_member",
            json={
                "space_id": space_id,
                "user_id": member_id,
                "encrypted_key": encrypted_key_hex
            }
        )
        resp.raise_for_status()
        return resp.json()

    def join_space(self, space_id: str) -> bytes:
        """Downloads and decrypts the space key."""
        resp = self.session.get(
            f"{self.backend_url}/api/spaces/{space_id}/key",
            params={"user_id": self.user_id}
        )
        resp.raise_for_status()
        data = resp.json()
        
        encrypted_key = data["encrypted_key"]
        creator_id = data["creator_id"]
        
        # Get creator public key
        creator_pubkey_pem = self._get_user_public_key(creator_id)
        
        # Derive shared key between member and creator
        shared_key = self._derive_shared_key(creator_pubkey_pem)
        
        # Decrypt space key
        space_key = self.decrypt_aes_gcm(shared_key, encrypted_key)
        self.space_keys[space_id] = space_key
        return space_key

    def send_dm(self, recipient_id: str, text: str) -> dict:
        """1-on-1 private messaging: encrypt and send."""
        recipient_pubkey_pem = self._get_user_public_key(recipient_id)
        shared_key = self._derive_shared_key(recipient_pubkey_pem)
        
        encrypted_payload = self.encrypt_aes_gcm(shared_key, text.encode('utf-8'))
        
        resp = self.session.post(
            f"{self.backend_url}/api/messages/send",
            json={
                "sender_id": self.user_id,
                "recipient_id": recipient_id,
                "payload_type": "text",
                "encrypted_payload": encrypted_payload
            }
        )
        resp.raise_for_status()
        return resp.json()

    def receive_dms(self) -> List[dict]:
        """Fetch and decrypt DM messages."""
        resp = self.session.get(
            f"{self.backend_url}/api/messages",
            params={"user_id": self.user_id}
        )
        resp.raise_for_status()
        messages = resp.json()
        
        decrypted_messages = []
        for msg in messages:
            # DMs have no space_id
            if msg.get("space_id") is None:
                sender_id = msg["sender_id"]
                recipient_id = msg["recipient_id"]
                peer_id = recipient_id if sender_id == self.user_id else sender_id
                
                peer_pubkey_pem = self._get_user_public_key(peer_id)
                shared_key = self._derive_shared_key(peer_pubkey_pem)
                
                decrypted_bytes = self.decrypt_aes_gcm(shared_key, msg["encrypted_payload"])
                decrypted_payload = decrypted_bytes.decode('utf-8')
                
                msg_copy = dict(msg)
                msg_copy["decrypted_payload"] = decrypted_payload
                decrypted_messages.append(msg_copy)
        return decrypted_messages

    def send_space_message(self, space_id: str, text: str) -> dict:
        """Encrypt message with space key and send."""
        space_key = self.space_keys.get(space_id)
        if not space_key:
            raise ValueError(f"No key for space {space_id} found locally")
            
        encrypted_payload = self.encrypt_aes_gcm(space_key, text.encode('utf-8'))
        
        resp = self.session.post(
            f"{self.backend_url}/api/messages/send",
            json={
                "sender_id": self.user_id,
                "space_id": space_id,
                "payload_type": "text",
                "encrypted_payload": encrypted_payload
            }
        )
        resp.raise_for_status()
        return resp.json()

    def receive_space_messages(self, space_id: str) -> List[dict]:
        """Fetch and decrypt space messages."""
        space_key = self.space_keys.get(space_id)
        if not space_key:
            raise ValueError(f"No key for space {space_id} found locally")
            
        resp = self.session.get(
            f"{self.backend_url}/api/messages",
            params={"space_id": space_id, "user_id": self.user_id}
        )
        resp.raise_for_status()
        messages = resp.json()
        
        decrypted_messages = []
        for msg in messages:
            decrypted_bytes = self.decrypt_aes_gcm(space_key, msg["encrypted_payload"])
            decrypted_payload = decrypted_bytes.decode('utf-8')
            
            msg_copy = dict(msg)
            msg_copy["decrypted_payload"] = decrypted_payload
            decrypted_messages.append(msg_copy)
        return decrypted_messages

    def schedule_meeting(self, target_id: str, is_space: bool, meeting_metadata: dict) -> dict:
        """Serialize meeting metadata to JSON, encrypt using space or DM key, and send."""
        # Validate required fields
        for field in ["title", "time", "location"]:
            if field not in meeting_metadata or not meeting_metadata[field]:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate time format
        time_str = meeting_metadata["time"]
        if not isinstance(time_str, str):
            raise ValueError("Time must be a string")
        time_str_norm = time_str
        if time_str_norm.endswith("Z"):
            time_str_norm = time_str_norm[:-1] + "+00:00"
        datetime.fromisoformat(time_str_norm)

        metadata_json = json.dumps(meeting_metadata)
        
        if is_space:
            key = self.space_keys.get(target_id)
            if not key:
                raise ValueError(f"No key for space {target_id} found locally")
            encrypted_payload = self.encrypt_aes_gcm(key, metadata_json.encode('utf-8'))
            json_body = {
                "sender_id": self.user_id,
                "space_id": target_id,
                "payload_type": "meeting",
                "encrypted_payload": encrypted_payload
            }
        else:
            recipient_pubkey_pem = self._get_user_public_key(target_id)
            key = self._derive_shared_key(recipient_pubkey_pem)
            encrypted_payload = self.encrypt_aes_gcm(key, metadata_json.encode('utf-8'))
            json_body = {
                "sender_id": self.user_id,
                "recipient_id": target_id,
                "payload_type": "meeting",
                "encrypted_payload": encrypted_payload
            }
            
        resp = self.session.post(
            f"{self.backend_url}/api/messages/send",
            json=json_body
        )
        resp.raise_for_status()
        return resp.json()

    def share_file(self, target_id: str, is_space: bool, file_name: str, file_bytes: bytes) -> dict:
        """Generate AES-256 file key, encrypt bytes, upload to backend, encrypt file key, send metadata."""
        # 1. Generate AES-256 file key
        file_key = AESGCM.generate_key(bit_length=256)
        
        # 2. Encrypt file bytes
        encrypted_file_bytes = self.encrypt_aes_gcm_bytes(file_key, file_bytes)
        
        # 3. Upload to backend
        files = {'file': (file_name, encrypted_file_bytes, 'application/octet-stream')}
        params = {
            "user_id": self.user_id
        }
        if is_space:
            params["space_id"] = target_id
        else:
            params["recipient_id"] = target_id
        resp = self.session.post(f"{self.backend_url}/api/files/upload", files=files, params=params)
        resp.raise_for_status()
        file_id = resp.json()["file_id"]
        
        # 4. Encrypt file key under channel key (space or DM)
        if is_space:
            channel_key = self.space_keys.get(target_id)
            if not channel_key:
                raise ValueError(f"No key for space {target_id} found locally")
        else:
            recipient_pubkey_pem = self._get_user_public_key(target_id)
            channel_key = self._derive_shared_key(recipient_pubkey_pem)
            
        encrypted_file_key_hex = self.encrypt_aes_gcm(channel_key, file_key)
        
        # 5. Encrypt metadata under channel key
        metadata = {
            "file_id": file_id,
            "file_name": file_name,
            "encrypted_file_key": encrypted_file_key_hex
        }
        metadata_json = json.dumps(metadata)
        encrypted_payload = self.encrypt_aes_gcm(channel_key, metadata_json.encode('utf-8'))
        
        # 6. Send message
        if is_space:
            json_body = {
                "sender_id": self.user_id,
                "space_id": target_id,
                "payload_type": "file",
                "encrypted_payload": encrypted_payload
            }
        else:
            json_body = {
                "sender_id": self.user_id,
                "recipient_id": target_id,
                "payload_type": "file",
                "encrypted_payload": encrypted_payload
            }
            
        resp = self.session.post(
            f"{self.backend_url}/api/messages/send",
            json=json_body
        )
        resp.raise_for_status()
        return resp.json()

    def download_and_decrypt_file(self, file_id: str, encrypted_file_key_hex: str, channel_key: bytes) -> bytes:
        """Download file and decrypt it using decrypted file key."""
        # 1. Decrypt file key
        file_key = self.decrypt_aes_gcm(channel_key, encrypted_file_key_hex)
        
        # 2. Download from backend
        resp = self.session.get(f"{self.backend_url}/api/files/download/{file_id}", params={"user_id": self.user_id})
        resp.raise_for_status()
        encrypted_file_bytes = resp.content
        
        # 3. Decrypt file bytes
        decrypted_file_bytes = self.decrypt_aes_gcm_bytes(file_key, encrypted_file_bytes)
        return decrypted_file_bytes

    def get_user_directory(self) -> List[dict]:
        """Fetch all registered users from backend."""
        resp = self.session.get(f"{self.backend_url}/api/users")
        resp.raise_for_status()
        return resp.json()

    def get_space_members(self, space_id: str) -> List[str]:
        """Fetch all members of a space."""
        resp = self.session.get(f"{self.backend_url}/api/spaces/{space_id}/members")
        resp.raise_for_status()
        return resp.json()["members"]

    def leave_space(self, space_id: str) -> dict:
        """Leave a space and delete local space key."""
        resp = self.session.post(
            f"{self.backend_url}/api/spaces/leave",
            json={
                "space_id": space_id,
                "user_id": self.user_id
            }
        )
        resp.raise_for_status()
        if space_id in self.space_keys:
            del self.space_keys[space_id]
        return resp.json()
