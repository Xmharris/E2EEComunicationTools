import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import time
import threading
import unittest
import json
import uvicorn

import requests

from secure_space_app.backend.app.main import app
from secure_space_app.tests.client_sim import ClientSim

class TestSecureSpaceE2E(unittest.TestCase):
    def setUp(self):
        requests.post(f"{self.backend_url}/api/reset").raise_for_status()

    @classmethod
    def setUpClass(cls):
        # Run mock backend in a daemon thread
        cls.backend_port = 8089
        cls.backend_url = f"http://127.0.0.1:{cls.backend_port}"
        
        import socket
        port_in_use = False
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", cls.backend_port)) == 0:
                port_in_use = True
                
        cls.server = None
        cls.thread = None
        
        if not port_in_use:
            cls.config = uvicorn.Config(
                app, 
                host="127.0.0.1", 
                port=cls.backend_port, 
                log_level="warning"
            )
            cls.server = uvicorn.Server(cls.config)
            cls.thread = threading.Thread(target=cls.server.run, daemon=True)
            cls.thread.start()
            # Wait for uvicorn to start up
            time.sleep(1.5)

    @classmethod
    def tearDownClass(cls):
        if cls.server is not None:
            cls.server.should_exit = True
            cls.thread.join(timeout=3)

    def test_e2e_flow(self):
        # 1. Instantiate and register clients
        alice = ClientSim("alice", self.backend_url)
        bob = ClientSim("bob", self.backend_url)
        
        alice_reg = alice.register()
        bob_reg = bob.register()
        
        self.assertEqual(alice_reg["status"], "registered")
        self.assertEqual(bob_reg["status"], "registered")

        # 2. Direct Messaging (DM)
        # Alice sends DM to Bob
        dm_text = "Hi Bob, this is a secret 1-on-1 message!"
        alice.send_dm("bob", dm_text)
        
        # Bob receives DMs
        bob_dms = bob.receive_dms()
        self.assertTrue(len(bob_dms) > 0)
        
        # Verify decrypted message contents
        alice_to_bob_msg = [m for m in bob_dms if m["sender_id"] == "alice"]
        self.assertTrue(len(alice_to_bob_msg) == 1)
        self.assertEqual(alice_to_bob_msg[0]["decrypted_payload"], dm_text)
        self.assertEqual(alice_to_bob_msg[0]["payload_type"], "text")

        # 3. Space Management & Key Distribution
        # Alice creates space1
        space_id = "space1"
        alice.create_space(space_id)
        
        # Alice adds Bob to space1
        alice.add_member_to_space(space_id, "bob")
        
        # Bob joins space1 and decrypts the space key
        bob_space_key = bob.join_space(space_id)
        
        # Verify that Bob has successfully decrypted the key and it matches Alice's key
        self.assertEqual(bob_space_key, alice.space_keys[space_id])

        # 4. Space Messaging
        # Alice sends a message to space1
        space_text = "Welcome to space1! Secrets only."
        alice.send_space_message(space_id, space_text)
        
        # Bob reads space1 messages
        bob_space_messages = bob.receive_space_messages(space_id)
        self.assertTrue(len(bob_space_messages) > 0)
        
        alice_space_msg = [m for m in bob_space_messages if m["sender_id"] == "alice" and m["payload_type"] == "text"]
        self.assertTrue(len(alice_space_msg) == 1)
        self.assertEqual(alice_space_msg[0]["decrypted_payload"], space_text)

        # 5. Meeting Scheduling
        # Alice schedules a meeting in space1
        meeting_meta = {
            "title": "Confidential Project Sync",
            "time": "2026-06-12T10:00:00Z",
            "location": "Virtual Room A"
        }
        alice.schedule_meeting(space_id, is_space=True, meeting_metadata=meeting_meta)
        
        # Bob retrieves meeting message
        bob_space_messages = bob.receive_space_messages(space_id)
        meeting_msgs = [m for m in bob_space_messages if m["payload_type"] == "meeting"]
        self.assertTrue(len(meeting_msgs) == 1)
        
        # Parse decrypted payload JSON
        decrypted_meeting_meta = json.loads(meeting_msgs[0]["decrypted_payload"])
        self.assertEqual(decrypted_meeting_meta["title"], meeting_meta["title"])
        self.assertEqual(decrypted_meeting_meta["time"], meeting_meta["time"])
        self.assertEqual(decrypted_meeting_meta["location"], meeting_meta["location"])

        # Alice schedules a DM meeting with Bob
        dm_meeting_meta = {
            "title": "Private Performance Review",
            "time": "2026-06-15T14:00:00Z",
            "location": "CEO Office"
        }
        alice.schedule_meeting("bob", is_space=False, meeting_metadata=dm_meeting_meta)
        
        bob_dms = bob.receive_dms()
        dm_meeting_msgs = [m for m in bob_dms if m["payload_type"] == "meeting"]
        self.assertTrue(len(dm_meeting_msgs) == 1)
        decrypted_dm_meeting = json.loads(dm_meeting_msgs[0]["decrypted_payload"])
        self.assertEqual(decrypted_dm_meeting["title"], dm_meeting_meta["title"])

        # 6. Content Sharing (File attachments)
        # Alice shares a file in space1
        file_name = "top_secret_plan.txt"
        file_content = b"The launch date is set for tomorrow at dawn."
        alice.share_file(space_id, is_space=True, file_name=file_name, file_bytes=file_content)
        
        # Bob reads space messages to find the file
        bob_space_messages = bob.receive_space_messages(space_id)
        file_msgs = [m for m in bob_space_messages if m["payload_type"] == "file"]
        self.assertTrue(len(file_msgs) == 1)
        
        # Bob decrypts the file metadata payload
        file_msg = file_msgs[0]
        file_msg_meta = json.loads(file_msg["decrypted_payload"])
        
        file_id = file_msg_meta["file_id"]
        encrypted_file_key = file_msg_meta["encrypted_file_key"]
        
        # Bob downloads and decrypts the file
        downloaded_bytes = bob.download_and_decrypt_file(
            file_id=file_id,
            encrypted_file_key_hex=encrypted_file_key,
            channel_key=bob_space_key
        )
        
        # Verify file content
        self.assertEqual(downloaded_bytes, file_content)

        # Alice shares a file in DM with Bob
        dm_file_name = "private_keynote.pdf"
        dm_file_content = b"%PDF-1.4 personal confidential memo content"
        alice.share_file("bob", is_space=False, file_name=dm_file_name, file_bytes=dm_file_content)
        
        # Bob retrieves DMs
        bob_dms = bob.receive_dms()
        dm_file_msgs = [m for m in bob_dms if m["payload_type"] == "file"]
        self.assertTrue(len(dm_file_msgs) == 1)
        
        dm_file_msg = dm_file_msgs[0]
        dm_file_meta = json.loads(dm_file_msg["decrypted_payload"])
        
        # Derive DM channel key (shared key between bob and alice)
        alice_pubkey_pem = bob._get_user_public_key("alice")
        dm_channel_key = bob._derive_shared_key(alice_pubkey_pem)
        
        dm_downloaded_bytes = bob.download_and_decrypt_file(
            file_id=dm_file_meta["file_id"],
            encrypted_file_key_hex=dm_file_meta["encrypted_file_key"],
            channel_key=dm_channel_key
        )
        
        self.assertEqual(dm_downloaded_bytes, dm_file_content)

if __name__ == "__main__":
    unittest.main()
