## 2026-06-12T07:44:01Z
You are the Worker (teamwork_preview_worker) for Milestone 4 (Adversarial Coverage Hardening).
Your working directory is: C:\Users\xavie\Documents\antigravity\quick-franklin\.agents\worker_m4
Your parent is: 1307d5e8-ef16-47b5-888e-233283d9326f

MANDATORY INTEGRITY WARNING:
DO NOT CHEAT. All implementations must be genuine. DO NOT hardcode test results, create dummy/facade implementations, or circumvent the intended task. A Forensic Auditor will independently verify your work. Integrity violations WILL be detected and your work WILL be rejected.

Task Description:
Your job is to:
1. Review the Challenger findings and test plans in:
   - C:\Users\xavie\Documents\antigravity\quick-franklin\.agents\teamwork_preview_challenger_m4_1\gap_report.md
   - C:\Users\xavie\Documents\antigravity\quick-franklin\.agents\teamwork_preview_challenger_m4_1\test_plan.md
   - C:\Users\xavie\Documents\antigravity\quick-franklin\.agents\teamwork_preview_challenger_m4_2\gap_report.md
   - C:\Users\xavie\Documents\antigravity\quick-franklin\.agents\teamwork_preview_challenger_m4_2\test_plan.md

2. Implement the proposed defenses in the backend (secure_space_app/backend/app/main.py) and update the clients (secure_space_app/tests/client_sim.py and Kotlin client files if needed):
   - In main.py:
     a) Implement token-based authentication. When a user registers via /api/users/register, generate a secure token (e.g. uuid.uuid4()) and return it.
     b) Save this token in the SQLite users table.
     c) For all endpoints requiring authorization, validate the incoming token (passed in "Authorization: Bearer <token>" header or query parameter "token").
     d) Perform strict access control checks. Ensure that the caller matches the user_id or is an authorized member/creator of the target space.
     e) Implement input validation: reject duplicate public keys to prevent identity collision; reject invalid public keys; restrict username length (< 100 char) and reject usernames with special characters (allow only [a-zA-Z0-9_-]+) or SQLi/XSS patterns.
     f) Restrict the /api/reset endpoint or ensure it only resets state for local test environments.
     g) Protect /api/files/download/{file_id} so that non-members are forbidden, and files uploaded with null metadata parameters are rejected for download.
   - In client_sim.py:
     a) Update the ClientSim class to handle and store the token returned during registration.
     b) Automatically append the "Authorization: Bearer <token>" header (or send token as query parameter/header) in all HTTP requests to the backend.
   - In ApiClient.kt and Models.kt:
     a) Add "token" field to RegisterResponse.
     b) Update ApiClient.kt to store the token upon registration and attach it as "Authorization: Bearer <token>" to subsequent HTTP requests.

3. Integrate the 10 adversarial E2E tests (Tier 5) designed by both Challengers into the E2E test suite (secure_space_app/tests/test_e2e_suite.py). Make sure these tests verify:
   - Unauthorized space membership changes fail.
   - User impersonation in message retrieval or file download is blocked.
   - Access to space keys or space member directory by non-members is blocked.
   - Replay attacks are attempted/detected.
   - Malicious usernames (SQLi/XSS) are rejected.
   - Duplicate public keys are rejected.
   - Tampered ciphertexts or tags fail cleanly (raising decryption exceptions) and don't crash the simulation.
   - IV misuse (short or missing IVs) raises clean value errors.
   - Eavesdropping by departed members who possess old space keys is prevented.

4. Run the build/compile and run the E2E tests via the test runner (python secure_space_app/tests/run_tests.py). Ensure that ALL 60 existing tests plus the new Tier 5 tests pass successfully.

Write your handoff report to:
- C:\Users\xavie\Documents\antigravity\quick-franklin\.agents\worker_m4\handoff.md

Update your progress.md regularly. Once finished and verified, send a message to your parent conversation ID.
