import sys
import os
import time
import json
import threading
import unittest
import requests
import uvicorn
import re
import datetime
import socket
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0

from secure_space_app.backend.app.main import app
from secure_space_app.tests.client_sim import ClientSim

class TestSecureSpaceE2E(unittest.TestCase):
    backend_port = 8089
    backend_url = f"http://127.0.0.1:{backend_port}"
    started_server = False

    @classmethod
    def setUpClass(cls):
        # Run mock backend in a daemon thread if not already running
        if is_port_in_use(cls.backend_port):
            # Check if it responds to HTTP requests
            try:
                requests.get(f"{cls.backend_url}/api/users", timeout=0.5)
                cls.started_server = False
                return
            except Exception:
                # Port is in use but not responding yet (maybe starting up). Wait a bit.
                for _ in range(20):
                    time.sleep(0.1)
                    try:
                        requests.get(f"{cls.backend_url}/api/users", timeout=0.1)
                        cls.started_server = False
                        return
                    except Exception:
                        pass
        
        cls.config = uvicorn.Config(
            app, 
            host="127.0.0.1", 
            port=cls.backend_port, 
            log_level="warning"
        )
        cls.server = uvicorn.Server(cls.config)
        cls.thread = threading.Thread(target=cls.server.run, daemon=True)
        cls.thread.start()
        cls.started_server = True
        
        # Wait for uvicorn to start up
        for _ in range(30):
            if is_port_in_use(cls.backend_port):
                break
            time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        if cls.started_server:
            cls.server.should_exit = True
            cls.thread.join(timeout=3)

    def setUp(self):
        # Reset the backend to a clean state before each test
        requests.post(f"{self.backend_url}/api/reset").raise_for_status()

    # ==========================================
    # TIER 1: FEATURE COVERAGE (25 TESTS)
    # ==========================================

    # --- Feature 1: User Registration & Public Key Registry ---

    def test_registration_success(self):
        alice = ClientSim("alice", self.backend_url)
        resp = alice.register()
        self.assertEqual(resp["status"], "registered")
        self.assertEqual(resp["user_id"], "alice")

    def test_registration_retrieves_pem(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        pem = alice._get_user_public_key("alice")
        self.assertEqual(pem, alice.get_public_key_pem())

    def test_multiple_users_registration(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        charlie = ClientSim("charlie", self.backend_url)
        
        alice.register()
        bob.register()
        charlie.register()
        
        self.assertEqual(alice._get_user_public_key("alice"), alice.get_public_key_pem())
        self.assertEqual(bob._get_user_public_key("bob"), bob.get_public_key_pem())
        self.assertEqual(charlie._get_user_public_key("charlie"), charlie.get_public_key_pem())

    def test_registration_response_structure(self):
        alice = ClientSim("alice", self.backend_url)
        resp = alice.register()
        self.assertIn("status", resp)
        self.assertIn("user_id", resp)
        self.assertIn("token", resp)
        self.assertEqual(len(resp), 3)

    def test_user_directory_contains_all(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        directory = alice.get_user_directory()
        user_ids = [u["user_id"] for u in directory]
        self.assertIn("alice", user_ids)
        self.assertIn("bob", user_ids)

    # --- Feature 2: Space/Channel Management ---

    def test_space_creation(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        resp = alice.create_space("space1")
        self.assertEqual(resp["status"], "created")
        self.assertEqual(resp["space_id"], "space1")

    def test_add_member_to_space(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        resp = alice.add_member_to_space("space1", "bob")
        self.assertEqual(resp["status"], "added")
        self.assertEqual(resp["space_id"], "space1")
        self.assertEqual(resp["user_id"], "bob")

    def test_retrieve_space_key(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob_space_key = bob.join_space("space1")
        self.assertEqual(bob_space_key, alice.space_keys["space1"])

    def test_space_member_list(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        
        members = alice.get_space_members("space1")
        self.assertIn("alice", members)
        self.assertIn("bob", members)

    def test_multiple_spaces_creation(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.create_space("space2")
        
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        self.assertIn("space1", alice.space_keys)
        self.assertIn("space2", alice.space_keys)
        self.assertIn("space1", bob.space_keys)
        self.assertNotIn("space2", bob.space_keys)

    # --- Feature 3: Direct Messaging (1-on-1 private messaging) ---

    def test_send_dm(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        resp = alice.send_dm("bob", "hello bob")
        self.assertEqual(resp["status"], "sent")

    def test_receive_dm(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.send_dm("bob", "message 1")
        bob_dms = bob.receive_dms()
        self.assertTrue(len(bob_dms) > 0)

    def test_dm_decryption(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.send_dm("bob", "top secret")
        bob_dms = bob.receive_dms()
        decrypted = [m for m in bob_dms if m["sender_id"] == "alice"][0]["decrypted_payload"]
        self.assertEqual(decrypted, "top secret")

    def test_dm_recipient_filtering(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        charlie = ClientSim("charlie", self.backend_url)
        alice.register()
        bob.register()
        charlie.register()
        
        alice.send_dm("bob", "only for bob")
        charlie_dms = charlie.receive_dms()
        self.assertEqual(len(charlie_dms), 0)

    def test_bidirectional_dm(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.send_dm("bob", "hi bob")
        bob.send_dm("alice", "hi alice")
        
        bob_dms = bob.receive_dms()
        alice_dms = alice.receive_dms()
        
        bob_received = [m for m in bob_dms if m["sender_id"] == "alice"]
        alice_received = [m for m in alice_dms if m["sender_id"] == "bob"]
        
        self.assertEqual(bob_received[0]["decrypted_payload"], "hi bob")
        self.assertEqual(alice_received[0]["decrypted_payload"], "hi alice")

    # --- Feature 4: Meeting Scheduling ---

    def test_schedule_meeting_in_space(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space1")
        
        meeting_meta = {"title": "Team Sync", "time": "2026-06-12T10:00:00Z", "location": "Virtual"}
        resp = alice.schedule_meeting("space1", is_space=True, meeting_metadata=meeting_meta)
        self.assertEqual(resp["status"], "sent")

    def test_receive_space_meeting(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        meeting_meta = {"title": "Team Sync", "time": "2026-06-12T10:00:00Z", "location": "Virtual"}
        alice.schedule_meeting("space1", is_space=True, meeting_metadata=meeting_meta)
        
        bob_msgs = bob.receive_space_messages("space1")
        meetings = [m for m in bob_msgs if m["payload_type"] == "meeting"]
        self.assertEqual(len(meetings), 1)

    def test_decrypt_space_meeting(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        meeting_meta = {"title": "Team Sync", "time": "2026-06-12T10:00:00Z", "location": "Virtual"}
        alice.schedule_meeting("space1", is_space=True, meeting_metadata=meeting_meta)
        
        bob_msgs = bob.receive_space_messages("space1")
        meeting = [m for m in bob_msgs if m["payload_type"] == "meeting"][0]
        meta = json.loads(meeting["decrypted_payload"])
        
        self.assertEqual(meta["title"], "Team Sync")
        self.assertEqual(meta["time"], "2026-06-12T10:00:00Z")

    def test_schedule_meeting_in_dm(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        meeting_meta = {"title": "1on1 Sync", "time": "2026-06-12T11:00:00Z", "location": "Virtual"}
        resp = alice.schedule_meeting("bob", is_space=False, meeting_metadata=meeting_meta)
        self.assertEqual(resp["status"], "sent")

    def test_decrypt_dm_meeting(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        meeting_meta = {"title": "1on1 Sync", "time": "2026-06-12T11:00:00Z", "location": "Virtual"}
        alice.schedule_meeting("bob", is_space=False, meeting_metadata=meeting_meta)
        
        bob_dms = bob.receive_dms()
        meeting = [m for m in bob_dms if m["payload_type"] == "meeting"][0]
        meta = json.loads(meeting["decrypted_payload"])
        
        self.assertEqual(meta["title"], "1on1 Sync")
        self.assertEqual(meta["location"], "Virtual")

    # --- Feature 5: Content Sharing ---

    def test_upload_file(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        
        file_key = AESGCM.generate_key(bit_length=256)
        enc_bytes = alice.encrypt_aes_gcm_bytes(file_key, b"secret data")
        
        resp = alice.session.post(f"{self.backend_url}/api/files/upload", files={'file': ('secret.txt', enc_bytes)}, params={"user_id": "alice"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("file_id", resp.json())

    def test_download_file(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        
        file_key = AESGCM.generate_key(bit_length=256)
        file_content = b"secret content"
        enc_bytes = alice.encrypt_aes_gcm_bytes(file_key, file_content)
        
        resp = alice.session.post(f"{self.backend_url}/api/files/upload", files={'file': ('secret.txt', enc_bytes)}, params={"user_id": "alice"})
        file_id = resp.json()["file_id"]
        
        downloaded = alice.download_and_decrypt_file(file_id, alice.encrypt_aes_gcm(file_key, file_key), file_key)
        self.assertEqual(downloaded, file_content)

    def test_share_file_in_space(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        resp = alice.share_file("space1", is_space=True, file_name="space_file.txt", file_bytes=b"hello space file")
        self.assertEqual(resp["status"], "sent")

    def test_share_file_in_dm(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        resp = alice.share_file("bob", is_space=False, file_name="dm_file.txt", file_bytes=b"hello dm file")
        self.assertEqual(resp["status"], "sent")

    def test_decrypt_shared_file(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        file_content = b"highly sensitive project info"
        alice.share_file("space1", is_space=True, file_name="project_info.txt", file_bytes=file_content)
        
        bob_msgs = bob.receive_space_messages("space1")
        file_msg = [m for m in bob_msgs if m["payload_type"] == "file"][0]
        meta = json.loads(file_msg["decrypted_payload"])
        
        downloaded = bob.download_and_decrypt_file(
            file_id=meta["file_id"],
            encrypted_file_key_hex=meta["encrypted_file_key"],
            channel_key=bob.space_keys["space1"]
        )
        self.assertEqual(downloaded, file_content)

    # ==========================================
    # TIER 2: BOUNDARY & CORNER CASES (25 TESTS)
    # ==========================================

    # --- Feature 1 Boundary Cases ---

    def test_register_duplicate_username(self):
        alice1 = ClientSim("alice", self.backend_url)
        alice1.register()
        alice2 = ClientSim("alice", self.backend_url)
        with self.assertRaises(requests.HTTPError) as ctx:
            alice2.register()
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_register_invalid_pem_key(self):
        resp = requests.post(
            f"{self.backend_url}/api/users/register",
            json={"user_id": "malicious", "public_key": "not a valid pem public key"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_register_empty_username(self):
        with self.assertRaises(requests.HTTPError) as ctx:
            ClientSim("", self.backend_url).register()
        self.assertEqual(ctx.exception.response.status_code, 400)
        
        with self.assertRaises(requests.HTTPError) as ctx:
            ClientSim("   ", self.backend_url).register()
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_register_extremely_long_username(self):
        long_username = "a" * 105
        with self.assertRaises(requests.HTTPError) as ctx:
            ClientSim(long_username, self.backend_url).register()
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_register_special_chars_username(self):
        with self.assertRaises(requests.HTTPError) as ctx:
            ClientSim("alice@domain.com", self.backend_url).register()
        self.assertEqual(ctx.exception.response.status_code, 400)

    # --- Feature 2 Boundary Cases ---

    def test_non_member_retrieve_space_key(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space1")
        
        bob = ClientSim("bob", self.backend_url)
        bob.register()
        
        with self.assertRaises(requests.HTTPError) as ctx:
            bob.join_space("space1")
        self.assertEqual(ctx.exception.response.status_code, 404)

    def test_add_non_existent_user_to_space(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space1")
        
        bob = ClientSim("bob", self.backend_url)
        bob.register()
        
        resp = requests.post(
            f"{self.backend_url}/api/spaces/add_member",
            json={
                "space_id": "space1",
                "user_id": "eve",
                "encrypted_key": "someencryptedkeyhex"
            },
            headers={"Authorization": f"Bearer {alice.token}"}
        )
        self.assertEqual(resp.status_code, 404)

    def test_add_member_duplicate(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        
        with self.assertRaises(requests.HTTPError) as ctx:
            alice.add_member_to_space("space1", "bob")
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_create_space_empty_name(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        
        with self.assertRaises(requests.HTTPError) as ctx:
            requests.post(
                f"{self.backend_url}/api/spaces/create",
                json={"space_id": "   ", "creator_id": "alice"},
                headers={"Authorization": f"Bearer {alice.token}"}
            ).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_retrieve_key_non_existent_space(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        
        with self.assertRaises(requests.HTTPError) as ctx:
            alice.join_space("non_existent_space")
        self.assertEqual(ctx.exception.response.status_code, 404)

    # --- Feature 3 Boundary Cases ---

    def test_send_dm_to_self(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        
        with self.assertRaises(requests.HTTPError) as ctx:
            alice.send_dm("alice", "hello me")
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_send_dm_to_non_existent_user(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        
        resp = requests.post(
            f"{self.backend_url}/api/messages/send",
            json={
                "sender_id": "alice",
                "recipient_id": "eve",
                "payload_type": "text",
                "encrypted_payload": "somepayload"
            },
            headers={"Authorization": f"Bearer {alice.token}"}
        )
        self.assertEqual(resp.status_code, 404)

    def test_send_empty_payload_dm(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        bob = ClientSim("bob", self.backend_url)
        bob.register()
        
        resp = requests.post(
            f"{self.backend_url}/api/messages/send",
            json={
                "sender_id": "alice",
                "recipient_id": "bob",
                "payload_type": "text",
                "encrypted_payload": " "
            },
            headers={"Authorization": f"Bearer {alice.token}"}
        )
        self.assertEqual(resp.status_code, 400)

    def test_dm_decrypt_with_wrong_key(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        charlie = ClientSim("charlie", self.backend_url)
        alice.register()
        bob.register()
        charlie.register()
        
        alice.send_dm("bob", "secret")
        
        # Charlie fetches Bob's incoming messages from Alice (using Bob's credentials to simulate Bob receiving)
        bob_dms = requests.get(
            f"{self.backend_url}/api/messages",
            params={"user_id": "bob"},
            headers={"Authorization": f"Bearer {bob.token}"}
        ).json()
        raw_msg = [m for m in bob_dms if m["sender_id"] == "alice"][0]["encrypted_payload"]
        
        # Charlie attempts to decrypt using Charlie-Alice shared key
        alice_pub = charlie._get_user_public_key("alice")
        shared = charlie._derive_shared_key(alice_pub)
        
        with self.assertRaises(Exception):
            charlie.decrypt_aes_gcm(shared, raw_msg)

    def test_send_dm_with_invalid_iv(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        bob = ClientSim("bob", self.backend_url)
        bob.register()
        
        pub = bob._get_user_public_key("alice")
        shared = bob._derive_shared_key(pub)
        
        # Invalid hex string containing too few bytes for IV
        with self.assertRaises(ValueError):
            bob.decrypt_aes_gcm(shared, "abcdef")

    # --- Feature 4 Boundary Cases ---

    def test_meeting_invalid_date_format(self):
        alice = ClientSim("alice", self.backend_url)
        with self.assertRaises(ValueError):
            alice.schedule_meeting("bob", is_space=False, meeting_metadata={
                "title": "Sync",
                "time": "next tuesday at noon",
                "location": "Room 101"
            })

    def test_meeting_missing_required_fields(self):
        alice = ClientSim("alice", self.backend_url)
        with self.assertRaises(ValueError):
            alice.schedule_meeting("bob", is_space=False, meeting_metadata={
                "title": "Sync"
            })

    def test_meeting_unauthorized_space_schedule(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space1")
        
        bob = ClientSim("bob", self.backend_url)
        bob.register()
        
        resp = bob.session.post(
            f"{self.backend_url}/api/messages/send",
            json={
                "sender_id": "bob",
                "space_id": "space1",
                "payload_type": "meeting",
                "encrypted_payload": "someencryptedpayload"
            }
        )
        self.assertEqual(resp.status_code, 403)

    def test_decrypt_meeting_with_wrong_space_key(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        meeting_meta = {"title": "Secret Meeting", "time": "2026-06-12T10:00:00Z", "location": "Room X"}
        alice.schedule_meeting("space1", is_space=True, meeting_metadata=meeting_meta)
        
        msgs = bob.session.get(f"{self.backend_url}/api/messages", params={"space_id": "space1", "user_id": "bob"}).json()
        raw_payload = [m for m in msgs if m["payload_type"] == "meeting"][0]["encrypted_payload"]
        
        wrong_key = AESGCM.generate_key(bit_length=256)
        with self.assertRaises(Exception):
            bob.decrypt_aes_gcm(wrong_key, raw_payload)

    def test_meeting_extremely_long_description(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        long_desc = "A" * 50000
        meeting_meta = {
            "title": "Team Sync",
            "time": "2026-06-12T10:00:00Z",
            "location": "Virtual",
            "description": long_desc
        }
        alice.schedule_meeting("space1", is_space=True, meeting_metadata=meeting_meta)
        
        bob_msgs = bob.receive_space_messages("space1")
        meeting = [m for m in bob_msgs if m["payload_type"] == "meeting"][0]
        meta = json.loads(meeting["decrypted_payload"])
        self.assertEqual(meta["description"], long_desc)

    # --- Feature 5 Boundary Cases ---

    def test_download_non_existent_file(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        resp = alice.session.get(f"{self.backend_url}/api/files/download/00000000-0000-0000-0000-000000000000")
        self.assertEqual(resp.status_code, 404)

    def test_upload_empty_file(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        files = {'file': ('empty.dat', b'')}
        resp = alice.session.post(f"{self.backend_url}/api/files/upload", files=files)
        self.assertEqual(resp.status_code, 400)

    def test_decrypt_file_wrong_key(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        
        file_key = AESGCM.generate_key(bit_length=256)
        enc_bytes = alice.encrypt_aes_gcm_bytes(file_key, b"confidential")
        
        resp = alice.session.post(f"{self.backend_url}/api/files/upload", files={'file': ('file.txt', enc_bytes)}, params={"user_id": "alice"})
        file_id = resp.json()["file_id"]
        
        resp_dl = alice.session.get(f"{self.backend_url}/api/files/download/{file_id}", params={"user_id": "alice"})
        dl_bytes = resp_dl.content
        
        wrong_file_key = AESGCM.generate_key(bit_length=256)
        with self.assertRaises(Exception):
            alice.decrypt_aes_gcm_bytes(wrong_file_key, dl_bytes)

    def test_share_file_non_member(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space1")
        
        bob = ClientSim("bob", self.backend_url)
        bob.register()
        
        # Bob uploads the file
        file_key = AESGCM.generate_key(bit_length=256)
        enc_file = bob.encrypt_aes_gcm_bytes(file_key, b"no access")
        resp_up = bob.session.post(f"{self.backend_url}/api/files/upload", files={'file': ('malicious.txt', enc_file)}, params={"user_id": "bob"})
        self.assertEqual(resp_up.status_code, 200)
        file_id = resp_up.json()["file_id"]
        
        # Bob tries to share in space1
        resp_msg = bob.session.post(
            f"{self.backend_url}/api/messages/send",
            json={
                "sender_id": "bob",
                "space_id": "space1",
                "payload_type": "file",
                "encrypted_payload": "someencryptedpayload"
            }
        )
        self.assertEqual(resp_msg.status_code, 403)

    def test_upload_large_file(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        
        large_bytes = os.urandom(1024 * 1024) # 1 MB
        file_key = AESGCM.generate_key(bit_length=256)
        enc_bytes = alice.encrypt_aes_gcm_bytes(file_key, large_bytes)
        
        resp = alice.session.post(f"{self.backend_url}/api/files/upload", files={'file': ('large.bin', enc_bytes)}, params={"user_id": "alice"})
        file_id = resp.json()["file_id"]
        
        dl_bytes = alice.session.get(f"{self.backend_url}/api/files/download/{file_id}", params={"user_id": "alice"}).content
        decrypted = alice.decrypt_aes_gcm_bytes(file_key, dl_bytes)
        self.assertEqual(decrypted, large_bytes)

    # ==========================================
    # TIER 3: CROSS-FEATURE COMBINATIONS (5 TESTS)
    # ==========================================

    def test_space_meeting_with_file_attachment(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        file_content = b"meeting handout"
        file_key = AESGCM.generate_key(bit_length=256)
        enc_file = alice.encrypt_aes_gcm_bytes(file_key, file_content)
        
        resp = alice.session.post(f"{self.backend_url}/api/files/upload", files={'file': ('handout.txt', enc_file)}, params={"user_id": "alice", "space_id": "space1"})
        file_id = resp.json()["file_id"]
        
        # Encrypt the file key under the space key
        space_key = alice.space_keys["space1"]
        enc_file_key = alice.encrypt_aes_gcm(space_key, file_key)
        
        meeting_meta = {
            "title": "Board Sync",
            "time": "2026-06-12T10:00:00Z",
            "location": "Boardroom",
            "attachment": {
                "file_id": file_id,
                "encrypted_file_key": enc_file_key
            }
        }
        alice.schedule_meeting("space1", is_space=True, meeting_metadata=meeting_meta)
        
        bob_msgs = bob.receive_space_messages("space1")
        meeting = [m for m in bob_msgs if m["payload_type"] == "meeting"][0]
        meta = json.loads(meeting["decrypted_payload"])
        att = meta["attachment"]
        
        downloaded = bob.download_and_decrypt_file(
            file_id=att["file_id"],
            encrypted_file_key_hex=att["encrypted_file_key"],
            channel_key=bob.space_keys["space1"]
        )
        self.assertEqual(downloaded, file_content)

    def test_dm_meeting_with_file_attachment(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        bob_pub = alice._get_user_public_key("bob")
        dm_key = alice._derive_shared_key(bob_pub)
        
        file_content = b"private criteria document"
        file_key = AESGCM.generate_key(bit_length=256)
        enc_file = alice.encrypt_aes_gcm_bytes(file_key, file_content)
        
        resp = alice.session.post(f"{self.backend_url}/api/files/upload", files={'file': ('criteria.txt', enc_file)}, params={"user_id": "alice", "recipient_id": "bob"})
        file_id = resp.json()["file_id"]
        
        enc_file_key = alice.encrypt_aes_gcm(dm_key, file_key)
        
        meeting_meta = {
            "title": "Review",
            "time": "2026-06-12T10:00:00Z",
            "location": "CEO Office",
            "attachment": {
                "file_id": file_id,
                "encrypted_file_key": enc_file_key
            }
        }
        alice.schedule_meeting("bob", is_space=False, meeting_metadata=meeting_meta)
        
        bob_dms = bob.receive_dms()
        meeting = [m for m in bob_dms if m["payload_type"] == "meeting"][0]
        meta = json.loads(meeting["decrypted_payload"])
        att = meta["attachment"]
        
        alice_pub = bob._get_user_public_key("alice")
        bob_dm_key = bob._derive_shared_key(alice_pub)
        
        downloaded = bob.download_and_decrypt_file(
            file_id=att["file_id"],
            encrypted_file_key_hex=att["encrypted_file_key"],
            channel_key=bob_dm_key
        )
        self.assertEqual(downloaded, file_content)

    def test_file_sharing_referencing_other_space_file(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        charlie = ClientSim("charlie", self.backend_url)
        
        alice.register()
        bob.register()
        charlie.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        file_content = b"draft paper"
        alice.share_file("space1", is_space=True, file_name="draft.txt", file_bytes=file_content)
        
        # Bob downloads draft from space1
        bob_msgs = bob.receive_space_messages("space1")
        f_msg = [m for m in bob_msgs if m["payload_type"] == "file"][0]
        f_meta = json.loads(f_msg["decrypted_payload"])
        
        downloaded = bob.download_and_decrypt_file(
            file_id=f_meta["file_id"],
            encrypted_file_key_hex=f_meta["encrypted_file_key"],
            channel_key=bob.space_keys["space1"]
        )
        
        # Bob shares downloaded draft in space2 with Charlie
        bob.create_space("space2")
        bob.add_member_to_space("space2", "charlie")
        charlie.join_space("space2")
        
        bob.share_file("space2", is_space=True, file_name="draft_v2.txt", file_bytes=downloaded)
        
        charlie_msgs = charlie.receive_space_messages("space2")
        charlie_f_msg = [m for m in charlie_msgs if m["payload_type"] == "file"][0]
        charlie_meta = json.loads(charlie_f_msg["decrypted_payload"])
        
        charlie_downloaded = charlie.download_and_decrypt_file(
            file_id=charlie_meta["file_id"],
            encrypted_file_key_hex=charlie_meta["encrypted_file_key"],
            channel_key=charlie.space_keys["space2"]
        )
        self.assertEqual(charlie_downloaded, file_content)

    def test_user_leaves_space_and_receives_dms(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        bob.leave_space("space1")
        
        # Alice sends space message
        alice.send_space_message("space1", "space secret")
        
        # Bob should fail to decrypt or fetch space messages
        with self.assertRaises(Exception):
            bob.receive_space_messages("space1")
            
        # Alice sends Bob a DM
        alice.send_dm("bob", "are you there?")
        
        # Bob receives DM successfully
        bob_dms = bob.receive_dms()
        dm = [m for m in bob_dms if m["sender_id"] == "alice"][0]
        self.assertEqual(dm["decrypted_payload"], "are you there?")

    def test_send_file_and_message_in_space_atomic_flow(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        file_content = b"atomic report content"
        file_key = AESGCM.generate_key(bit_length=256)
        enc_file = alice.encrypt_aes_gcm_bytes(file_key, file_content)
        
        resp = alice.session.post(f"{self.backend_url}/api/files/upload", files={'file': ('report.txt', enc_file)}, params={"user_id": "alice", "space_id": "space1"})
        file_id = resp.json()["file_id"]
        
        enc_file_key = alice.encrypt_aes_gcm(alice.space_keys["space1"], file_key)
        
        # Share file reference inside a normal space text message
        nested_meta = {"file_id": file_id, "encrypted_file_key": enc_file_key}
        alice.send_space_message("space1", json.dumps(nested_meta))
        
        bob_msgs = bob.receive_space_messages("space1")
        txt_msg = [m for m in bob_msgs if m["payload_type"] == "text"][0]
        
        parsed = json.loads(txt_msg["decrypted_payload"])
        downloaded = bob.download_and_decrypt_file(
            file_id=parsed["file_id"],
            encrypted_file_key_hex=parsed["encrypted_file_key"],
            channel_key=bob.space_keys["space1"]
        )
        self.assertEqual(downloaded, file_content)

    # ==========================================
    # TIER 4: REAL-WORLD SCENARIOS (5 TESTS)
    # ==========================================

    def test_multi_user_onboarding_and_secure_setup(self):
        # 5 users onboard, establish spaces and keys
        users = ["alice", "bob", "charlie", "david", "eve"]
        clients = {}
        for u in users:
            clients[u] = ClientSim(u, self.backend_url)
            clients[u].register()
            
        # Alice creates Space A (alice, bob, charlie)
        clients["alice"].create_space("spaceA")
        clients["alice"].add_member_to_space("spaceA", "bob")
        clients["alice"].add_member_to_space("spaceA", "charlie")
        clients["bob"].join_space("spaceA")
        clients["charlie"].join_space("spaceA")
        
        # Charlie creates Space B (charlie, david, eve)
        clients["charlie"].create_space("spaceB")
        clients["charlie"].add_member_to_space("spaceB", "david")
        clients["charlie"].add_member_to_space("spaceB", "eve")
        clients["david"].join_space("spaceB")
        clients["eve"].join_space("spaceB")
        
        self.assertEqual(clients["alice"].space_keys["spaceA"], clients["bob"].space_keys["spaceA"])
        self.assertEqual(clients["alice"].space_keys["spaceA"], clients["charlie"].space_keys["spaceA"])
        self.assertEqual(clients["charlie"].space_keys["spaceB"], clients["david"].space_keys["spaceB"])
        self.assertEqual(clients["charlie"].space_keys["spaceB"], clients["eve"].space_keys["spaceB"])

    def test_wire_level_encryption_verification(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("space1")
        alice.add_member_to_space("space1", "bob")
        bob.join_space("space1")
        
        alice.send_space_message("space1", "very secret text in space")
        alice.send_dm("bob", "very secret text in dm")
        
        # Query space messages (requires space membership)
        resp_space = alice.session.get(f"{self.backend_url}/api/messages", params={"space_id": "space1", "user_id": "alice"})
        space_msgs = resp_space.json()
        
        # Query DM messages (requires user involvement)
        resp_dm = alice.session.get(f"{self.backend_url}/api/messages", params={"user_id": "alice"})
        dm_msgs = resp_dm.json()
        
        raw_msgs = space_msgs + dm_msgs
        
        for msg in raw_msgs:
            payload = msg["encrypted_payload"]
            self.assertNotIn("very secret", payload.lower())
            self.assertNotIn("text", payload.lower())
            self.assertNotIn("space", payload.lower())
            self.assertNotIn("dm", payload.lower())
            # Ensure it is a valid hex string
            bytes.fromhex(payload)

    def test_key_agreement_verification(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        charlie = ClientSim("charlie", self.backend_url)
        
        alice.register()
        bob.register()
        charlie.register()
        
        alice_bob_pub = alice._get_user_public_key("bob")
        key_alice_bob = alice._derive_shared_key(alice_bob_pub)
        
        bob_alice_pub = bob._get_user_public_key("alice")
        key_bob_alice = bob._derive_shared_key(bob_alice_pub)
        
        # Verify ECDH symmetry
        self.assertEqual(key_alice_bob, key_bob_alice)
        
        # Verify Charlie cannot guess or derive the same key
        charlie_alice_pub = charlie._get_user_public_key("alice")
        key_charlie_alice = charlie._derive_shared_key(charlie_alice_pub)
        self.assertNotEqual(key_alice_bob, key_charlie_alice)

    def test_secure_collaborative_workflow(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()
        
        alice.create_space("collab_space")
        alice.add_member_to_space("collab_space", "bob")
        bob.join_space("collab_space")
        
        # 1. Schedule meeting to plan
        alice.schedule_meeting("collab_space", is_space=True, meeting_metadata={"title": "Planning", "time": "2026-06-12T09:00:00Z", "location": "Room 1"})
        
        # 2. Alice uploads version 1 file
        v1_data = b"Initial proposal details"
        alice.share_file("collab_space", is_space=True, file_name="proposal.txt", file_bytes=v1_data)
        
        # 3. Bob receives meeting notification, downloads proposal v1
        bob_msgs = bob.receive_space_messages("collab_space")
        m_msg = [m for m in bob_msgs if m["payload_type"] == "meeting"][0]
        f_msg = [m for m in bob_msgs if m["payload_type"] == "file"][0]
        
        meta = json.loads(f_msg["decrypted_payload"])
        bob_dl = bob.download_and_decrypt_file(meta["file_id"], meta["encrypted_file_key"], bob.space_keys["collab_space"])
        self.assertEqual(bob_dl, v1_data)
        
        # 4. Bob reviews, updates file to version 2, and uploads it
        v2_data = bob_dl + b"\nApproved by Bob"
        bob.share_file("collab_space", is_space=True, file_name="proposal_final.txt", file_bytes=v2_data)
        
        # 5. Alice downloads final proposal version 2
        alice_msgs = alice.receive_space_messages("collab_space")
        f_final = [m for m in alice_msgs if m["payload_type"] == "file" and json.loads(m["decrypted_payload"])["file_name"] == "proposal_final.txt"][0]
        final_meta = json.loads(f_final["decrypted_payload"])
        alice_dl = alice.download_and_decrypt_file(final_meta["file_id"], final_meta["encrypted_file_key"], alice.space_keys["collab_space"])
        
        self.assertEqual(alice_dl, v2_data)

    def test_unauthorized_eavesdropping_prevention(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        eve = ClientSim("eve", self.backend_url)
        
        alice.register()
        bob.register()
        eve.register()
        
        alice.create_space("confidential")
        alice.add_member_to_space("confidential", "bob")
        bob.join_space("confidential")
        
        # Alice sends space message and files
        alice.send_space_message("confidential", "critical secure space talk")
        alice.share_file("confidential", is_space=True, file_name="secret.txt", file_bytes=b"eve must not see this")
        
        # Eve tries to fetch key of space 'confidential' -> HTTP 404/403
        with self.assertRaises(requests.HTTPError):
            eve.session.get(f"{self.backend_url}/api/spaces/confidential/key", params={"user_id": "eve"}).raise_for_status()
            
        # Eve queries messages of space 'confidential' -> HTTP 403 Forbidden
        resp_msgs = eve.session.get(f"{self.backend_url}/api/messages", params={"space_id": "confidential", "user_id": "eve"})
        self.assertEqual(resp_msgs.status_code, 403)
                
        # Alice (who is authorized) downloads/reads the message to get the file_id
        alice_msgs = alice.receive_space_messages("confidential")
        file_msg = [m for m in alice_msgs if m["payload_type"] == "file"][0]
        meta = json.loads(file_msg["decrypted_payload"])
        file_id = meta["file_id"]
        
        # Alice (authorized) downloads the file successfully
        resp_dl_alice = alice.session.get(f"{self.backend_url}/api/files/download/{file_id}", params={"user_id": "alice"})
        self.assertEqual(resp_dl_alice.status_code, 200)
        
        # Eve (unauthorized) tries to download the file -> HTTP 403 Forbidden
        resp_dl_eve = eve.session.get(f"{self.backend_url}/api/files/download/{file_id}", params={"user_id": "eve"})
        self.assertEqual(resp_dl_eve.status_code, 403)

    def test_adv_unauthorized_space_membership_manipulation(self):
        # 1. Register alice (creator) and bob (recipient)
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space_secure")

        bob = ClientSim("bob", self.backend_url)
        bob.register()

        # Register eve (unauthorized third-party)
        eve = ClientSim("eve", self.backend_url)
        eve.register()

        # 2. Eve attempts to add Bob to Alice's space_secure -> Expect 403
        with self.assertRaises(requests.HTTPError) as ctx:
            eve.session.post(
                f"{self.backend_url}/api/spaces/add_member",
                json={
                    "space_id": "space_secure",
                    "user_id": "bob",
                    "encrypted_key": "fakekey"
                }
            ).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 403)

        # 3. Eve attempts to add herself to Alice's space_secure -> Expect 403
        with self.assertRaises(requests.HTTPError) as ctx:
            eve.session.post(
                f"{self.backend_url}/api/spaces/add_member",
                json={
                    "space_id": "space_secure",
                    "user_id": "eve",
                    "encrypted_key": "fakekey"
                }
            ).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 403)

        # 4. Eve attempts to force Alice (the creator) out of space_secure -> Expect 403
        with self.assertRaises(requests.HTTPError) as ctx:
            eve.session.post(
                f"{self.backend_url}/api/spaces/leave",
                json={
                    "space_id": "space_secure",
                    "user_id": "alice"
                }
            ).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 403)

        # 5. Verify space membership list for space_secure only contains alice
        members = alice.get_space_members("space_secure")
        self.assertEqual(members, ["alice"])

    def test_adv_user_impersonation_in_messages_blocked(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space_private")
        alice.send_space_message("space_private", "confidential text")

        bob = ClientSim("bob", self.backend_url)
        bob.register()

        # Bob attempts to read space_private messages by impersonating alice -> Expect 403
        with self.assertRaises(requests.HTTPError) as ctx:
            bob.session.get(f"{self.backend_url}/api/messages", params={"space_id": "space_private", "user_id": "alice"}).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 403)

    def test_adv_user_impersonation_in_file_download_blocked(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space_private")
        
        # Alice uploads a file
        file_bytes = b"highly sensitive content"
        resp_up = alice.session.post(
            f"{self.backend_url}/api/files/upload",
            files={"file": ("secret.txt", file_bytes)},
            params={"user_id": "alice", "space_id": "space_private"}
        )
        file_id = resp_up.json()["file_id"]

        eve = ClientSim("eve", self.backend_url)
        eve.register()

        # Eve attempts to download the file using user_id=alice (impersonation) -> Expect 403
        with self.assertRaises(requests.HTTPError) as ctx:
            eve.session.get(f"{self.backend_url}/api/files/download/{file_id}", params={"user_id": "alice"}).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 403)

    def test_adv_non_member_access_to_space_keys_blocked(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space_confidential")

        eve = ClientSim("eve", self.backend_url)
        eve.register()

        # Eve tries to retrieve Alice's space key -> Expect 403
        with self.assertRaises(requests.HTTPError) as ctx:
            eve.session.get(f"{self.backend_url}/api/spaces/space_confidential/key", params={"user_id": "alice"}).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 403)

    def test_adv_non_member_access_to_space_members_blocked(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        alice.create_space("space_confidential")

        eve = ClientSim("eve", self.backend_url)
        eve.register()

        # Eve tries to retrieve space members list -> Expect 403
        with self.assertRaises(requests.HTTPError) as ctx:
            eve.session.get(f"{self.backend_url}/api/spaces/space_confidential/members").raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 403)

    def test_adv_replay_attacks_attempted_and_detected(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        bob = ClientSim("bob", self.backend_url)
        bob.register()

        # Send DM
        resp_send = alice.send_dm("bob", "Approve Transaction")
        self.assertEqual(resp_send["status"], "sent")

        # Fetch DM to get payload
        bob_dms = bob.receive_dms()
        dm = [m for m in bob_dms if m["sender_id"] == "alice"][0]
        encrypted_payload = dm["encrypted_payload"]

        # Attempt to replay the payload -> Expect 400 Bad Request
        with self.assertRaises(requests.HTTPError) as ctx:
            alice.session.post(
                f"{self.backend_url}/api/messages/send",
                json={
                    "sender_id": "alice",
                    "recipient_id": "bob",
                    "payload_type": "text",
                    "encrypted_payload": encrypted_payload
                }
            ).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_adv_malicious_usernames_rejected(self):
        # 1. SQL Injection attempt in user registration -> Expect 400
        with self.assertRaises(requests.HTTPError) as ctx:
            requests.post(
                f"{self.backend_url}/api/users/register",
                json={"user_id": "alice' OR '1'='1", "public_key": "dummy"}
            ).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 400)

        # 2. XSS attempt in user registration -> Expect 400
        with self.assertRaises(requests.HTTPError) as ctx:
            requests.post(
                f"{self.backend_url}/api/users/register",
                json={"user_id": "<script>alert(1)</script>", "public_key": "dummy"}
            ).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_adv_duplicate_public_keys_rejected(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()

        # bob tries to register using Alice's public key -> Expect 400
        with self.assertRaises(requests.HTTPError) as ctx:
            requests.post(
                f"{self.backend_url}/api/users/register",
                json={"user_id": "bob", "public_key": alice.get_public_key_pem()}
            ).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 400)

    def test_adv_tampered_ciphertexts_or_tags_fail_cleanly(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        bob = ClientSim("bob", self.backend_url)
        bob.register()

        alice.send_dm("bob", "Confidential Message")
        
        # Get bob's raw messages from backend
        bob_dms = bob.session.get(f"{self.backend_url}/api/messages", params={"user_id": "bob"}).json()
        raw_payload = [m for m in bob_dms if m["sender_id"] == "alice"][0]["encrypted_payload"]

        # Flip a bit in the ciphertext bytes
        data = bytearray(bytes.fromhex(raw_payload))
        data[20] ^= 1 # corrupt a byte after the first 12 bytes (IV)
        corrupted_payload = data.hex()

        # Decrypting should raise an exception cleanly
        peer_pub = bob._get_user_public_key("alice")
        shared_key = bob._derive_shared_key(peer_pub)

        with self.assertRaises(Exception):
            bob.decrypt_aes_gcm(shared_key, corrupted_payload)

    def test_adv_iv_misuse_raises_clean_errors(self):
        alice = ClientSim("alice", self.backend_url)
        alice.register()
        bob = ClientSim("bob", self.backend_url)
        bob.register()

        peer_pub = bob._get_user_public_key("alice")
        shared_key = bob._derive_shared_key(peer_pub)

        # Payload A: A hex string of 10 bytes (too short)
        payload_short = "aabbccddeeff00112233"
        with self.assertRaises(ValueError) as ctx:
            bob.decrypt_aes_gcm(shared_key, payload_short)
        self.assertIn("too short", str(ctx.exception).lower())

        # Payload B: empty ciphertext (exactly 12 bytes IV only)
        payload_iv_only = "00" * 12
        with self.assertRaises(Exception):
            bob.decrypt_aes_gcm(shared_key, payload_iv_only)

    def test_adv_eavesdropping_by_departed_members_blocked(self):
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        alice.register()
        bob.register()

        alice.create_space("collab_space")
        alice.add_member_to_space("collab_space", "bob")
        bob.join_space("collab_space")

        # Bob leaves space
        bob.leave_space("collab_space")

        # Alice sends space message and files
        alice.send_space_message("collab_space", "Confidential Future Talk")
        file_bytes = b"eve must not see this"
        resp_up = alice.session.post(
            f"{self.backend_url}/api/files/upload",
            files={"file": ("secret.txt", file_bytes)},
            params={"user_id": "alice", "space_id": "collab_space"}
        )
        file_id = resp_up.json()["file_id"]

        # Bob (now departed) tries to fetch space messages -> Expect 403
        with self.assertRaises(requests.HTTPError) as ctx:
            bob.session.get(f"{self.backend_url}/api/messages", params={"space_id": "collab_space", "user_id": "bob"}).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 403)

        # Bob tries to download space file -> Expect 403
        with self.assertRaises(requests.HTTPError) as ctx:
            bob.session.get(f"{self.backend_url}/api/files/download/{file_id}", params={"user_id": "bob"}).raise_for_status()
        self.assertEqual(ctx.exception.response.status_code, 403)

    def test_adv_null_metadata_files_rejected_for_download(self):
        eve = ClientSim("eve", self.backend_url)
        eve.register()

        # Eve uploads a file with no metadata
        resp_null_up = eve.session.post(
            f"{self.backend_url}/api/files/upload",
            files={"file": ("null_file.txt", b"some data")}
        )
        null_file_id = resp_null_up.json()["file_id"]

        # Anyone (or Eve without a user_id) attempts to download -> Expect 403 or 401
        with self.assertRaises(requests.HTTPError) as ctx:
            requests.get(f"{self.backend_url}/api/files/download/{null_file_id}").raise_for_status()
        self.assertIn(ctx.exception.response.status_code, (401, 403))

if __name__ == "__main__":
    unittest.main()

