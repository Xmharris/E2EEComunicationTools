import unittest
import os
import sys
from fastapi.testclient import TestClient
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

# Add the backend app folder to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from secure_space_app.backend.app.main import app, get_db

class TestBackendAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        # Generate a valid public key for testing
        cls.private_key = ec.generate_private_key(ec.SECP256R1())
        cls.public_key_pem = cls.private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

    def setUp(self):
        # Reset database before each test
        response = self.client.post("/api/reset")
        self.assertEqual(response.status_code, 200)

    def test_reset_backend(self):
        response = self.client.post("/api/reset")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "reset"})

    def test_register_user_success(self):
        response = self.client.post(
            "/api/users/register",
            json={"user_id": "alice", "public_key": self.public_key_pem}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "registered", "user_id": "alice"})

        # Verify in get_users
        response = self.client.get("/api/users")
        self.assertEqual(response.status_code, 200)
        users = response.json()
        self.assertEqual(len(users), 1)
        self.assertEqual(users[0]["user_id"], "alice")
        self.assertEqual(users[0]["public_key"], self.public_key_pem)

    def test_register_user_failures(self):
        # Empty user_id
        response = self.client.post(
            "/api/users/register",
            json={"user_id": "   ", "public_key": self.public_key_pem}
        )
        self.assertEqual(response.status_code, 400)

        # Duplicate user_id
        self.client.post(
            "/api/users/register",
            json={"user_id": "alice", "public_key": self.public_key_pem}
        )
        response = self.client.post(
            "/api/users/register",
            json={"user_id": "alice", "public_key": self.public_key_pem}
        )
        self.assertEqual(response.status_code, 400)

        # Invalid PEM
        response = self.client.post(
            "/api/users/register",
            json={"user_id": "bob", "public_key": "invalid-pem-format"}
        )
        self.assertEqual(response.status_code, 400)

        # Long username
        response = self.client.post(
            "/api/users/register",
            json={"user_id": "a" * 101, "public_key": self.public_key_pem}
        )
        self.assertEqual(response.status_code, 400)

        # Invalid characters
        response = self.client.post(
            "/api/users/register",
            json={"user_id": "alice@bob", "public_key": self.public_key_pem}
        )
        self.assertEqual(response.status_code, 400)

    def test_spaces_create_and_members(self):
        # Register creator
        self.client.post(
            "/api/users/register",
            json={"user_id": "alice", "public_key": self.public_key_pem}
        )

        # Create space
        response = self.client.post(
            "/api/spaces/create",
            json={"space_id": "space1", "creator_id": "alice"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "created", "space_id": "space1"})

        # Duplicate space
        response = self.client.post(
            "/api/spaces/create",
            json={"space_id": "space1", "creator_id": "alice"}
        )
        self.assertEqual(response.status_code, 400)

        # Creator not found
        response = self.client.post(
            "/api/spaces/create",
            json={"space_id": "space2", "creator_id": "unregistered"}
        )
        self.assertEqual(response.status_code, 404)

        # Add member
        response = self.client.post(
            "/api/spaces/add_member",
            json={"space_id": "space1", "user_id": "alice", "encrypted_key": "enc_key_123"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "added", "space_id": "space1", "user_id": "alice"})

        # Get space key
        response = self.client.get("/api/spaces/space1/key?user_id=alice")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["space_id"], "space1")
        self.assertEqual(data["user_id"], "alice")
        self.assertEqual(data["encrypted_key"], "enc_key_123")
        self.assertEqual(data["creator_id"], "alice")

        # Get members
        response = self.client.get("/api/spaces/space1/members")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"space_id": "space1", "members": ["alice"]})

        # Leave space
        response = self.client.post(
            "/api/spaces/leave",
            json={"space_id": "space1", "user_id": "alice"}
        )
        self.assertEqual(response.status_code, 200)

        # Verify key is deleted
        response = self.client.get("/api/spaces/space1/key?user_id=alice")
        self.assertEqual(response.status_code, 404)

    def test_messages_flow(self):
        # Register users
        self.client.post(
            "/api/users/register",
            json={"user_id": "alice", "public_key": self.public_key_pem}
        )
        self.client.post(
            "/api/users/register",
            json={"user_id": "bob", "public_key": self.public_key_pem}
        )

        # Send DM
        response = self.client.post(
            "/api/messages/send",
            json={
                "sender_id": "alice",
                "recipient_id": "bob",
                "payload_type": "text",
                "encrypted_payload": "secret_dm"
            }
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("message_id", response.json())

        # Retrieve messages
        response = self.client.get("/api/messages?user_id=alice")
        self.assertEqual(response.status_code, 200)
        msgs = response.json()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]["sender_id"], "alice")
        self.assertEqual(msgs[0]["recipient_id"], "bob")
        self.assertEqual(msgs[0]["encrypted_payload"], "secret_dm")

    def test_files_upload_download(self):
        file_content = b"my secure file contents"
        response = self.client.post(
            "/api/files/upload?user_id=alice",
            files={"file": ("test.bin", file_content, "application/octet-stream")}
        )
        self.assertEqual(response.status_code, 200)
        file_id = response.json()["file_id"]
        self.assertIsNotNone(file_id)

        # Download file without user_id -> 403 Forbidden
        response = self.client.get(f"/api/files/download/{file_id}")
        self.assertEqual(response.status_code, 403)

        # Download file with wrong user_id -> 403 Forbidden
        response = self.client.get(f"/api/files/download/{file_id}?user_id=bob")
        self.assertEqual(response.status_code, 403)

        # Download file with correct user_id -> 200 OK
        response = self.client.get(f"/api/files/download/{file_id}?user_id=alice")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, file_content)

        # Download non-existent file -> 404 Not Found
        response = self.client.get("/api/files/download/nonexistent?user_id=alice")
        self.assertEqual(response.status_code, 404)

if __name__ == "__main__":
    unittest.main()
