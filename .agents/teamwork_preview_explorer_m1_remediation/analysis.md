# Forensic Audit Remediation Exploration Report

## Executive Summary
This report analyzes the discrepancies between the real SQLite backend (`secure_space_app/backend/app/main.py`) and the mock backend (`secure_space_app/tests/mock_backend.py`), designs schema and API changes to implement proper access controls on the real backend, and provides a clear plan to update the test configuration to run E2E tests against the real database-backed application.

A critical order-of-operation discrepancy has been identified in the file download endpoint `/api/files/download/{file_id}`. In the real backend, missing `user_id` validation is performed *before* checking file existence, causing test failures (returns `403 Forbidden` instead of `404 Not Found`). In the mock backend, file existence is verified first. Correcting this discrepancy is necessary for all tests to pass successfully against the real backend.

---

## 1. Comparison of Endpoint Implementations

### A. Message Retrieval (`GET /api/messages`)
* **Mock Backend (`mock_backend.py`)**:
  - Requires `user_id` query parameter (raises `403 Forbidden` if missing).
  - For space messages (`space_id` provided):
    - Verifies space exists in `spaces_db` (raises `404 Not Found`).
    - Verifies user membership in `space_keys_db` (raises `403 Forbidden`).
    - Returns messages filtered by `space_id`.
  - For direct messages (`space_id` not provided):
    - Returns messages where the user is either the sender or recipient.
* **Real Backend (`main.py`)**:
  - The endpoint has been updated to include identical access controls. It validates the presence of `user_id`, checks the `spaces` table for existence, queries the `space_keys` table to verify membership, and retrieves relevant messages from the database using SQL queries.

### B. File Download (`GET /api/files/download/{file_id}`)
* **Mock Backend (`mock_backend.py`)**:
  - First retrieves the file bytes. If the file is not found, raises `404 Not Found`.
  - If the file exists, checks for stored metadata.
  - If metadata is present:
    - Requires `user_id` query parameter (raises `403 Forbidden` if missing).
    - Checks uploader (owner), space membership (if shared in a space), or direct recipient (if a DM). If unauthorized, raises `403 Forbidden`.
* **Real Backend (`main.py`)**:
  - Currently enforces the check `if not user_id: raise HTTPException(403)` at the very beginning of the handler.
  - Subsequently queries the database for the file. If the file is not found, raises `404 Not Found`.
  - Enforces authorization logic matching the mock backend.
  - **Critical Discrepancy**: Because the `user_id` check occurs first, a request for a non-existent file without `user_id` returns `403 Forbidden`. This causes the E2E test `test_download_non_existent_file` (which requests a dummy ID without a user query param) to fail with an assertion error (`403 != 404`).

---

## 2. SQLite Files Table Schema Updates
To support metadata storage, the `files` table must be updated to store `user_id` (uploader), `space_id` (target space, if any), and `recipient_id` (DM recipient, if any).

### Schema SQL:
```sql
CREATE TABLE IF NOT EXISTS files (
    file_id TEXT PRIMARY KEY,
    file_bytes BLOB NOT NULL,
    user_id TEXT,
    space_id TEXT,
    recipient_id TEXT
)
```

### Database Initialization:
Since the backend application removes the SQLite database file on startup if it exists, updating the `CREATE TABLE` query directly in `init_db()` is sufficient to apply the schema without migrations.

```python
# Initialize database tables on startup
if os.path.exists(DB_PATH):
    try:
        os.remove(DB_PATH)
    except Exception:
        pass
init_db()
```

---

## 3. SQL Queries & Validation Logic

### A. Message Retrieval Endpoint (`GET /api/messages`)
The endpoint retrieves messages with the following logic:
1. Validate `user_id` parameter.
2. If `space_id` is provided:
   - Query `spaces` table to check existence: `SELECT 1 FROM spaces WHERE space_id = ?`
   - Query `space_keys` to verify membership: `SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?`
   - Fetch space messages: `SELECT id, sender_id, recipient_id, space_id, payload_type, encrypted_payload FROM messages WHERE space_id = ?`
3. If `space_id` is not provided:
   - Fetch DM messages: `SELECT id, sender_id, recipient_id, space_id, payload_type, encrypted_payload FROM messages WHERE space_id IS NULL AND (sender_id = ? OR recipient_id = ?)`

### B. File Upload Endpoint (`POST /api/files/upload`)
Query parameters are captured and inserted into the database:
```python
@app.post("/api/files/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: Optional[str] = Query(None),
    space_id: Optional[str] = Query(None),
    recipient_id: Optional[str] = Query(None)
):
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
```

### C. File Download Endpoint (`GET /api/files/download/{file_id}`)
To match the mock backend, file existence check must precede query validation:
```python
@app.get("/api/files/download/{file_id}")
def download_file(file_id: str, user_id: Optional[str] = Query(None)):
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
    
    # Access controls are only enforced if metadata is associated with the file
    if uploader or space_id or recipient_id:
        if not user_id:
            raise HTTPException(status_code=403, detail="Forbidden: user_id is required")
            
        # 1. Owner/Uploader bypass
        if user_id == uploader:
            pass
        # 2. Space membership check
        elif space_id is not None:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM space_keys WHERE space_id = ? AND user_id = ?", (space_id, user_id))
            member_row = cursor.fetchone()
            conn.close()
            if not member_row:
                raise HTTPException(status_code=403, detail="Forbidden: User is not a member of the space")
        # 3. DM participant check
        elif recipient_id is not None:
            if user_id != recipient_id and user_id != uploader:
                raise HTTPException(status_code=403, detail="Forbidden: User is not the recipient or uploader")
        # 4. Fallback owner check
        else:
            if user_id != uploader:
                raise HTTPException(status_code=403, detail="Forbidden: User is not the uploader")
                
    return Response(content=row["file_bytes"], media_type="application/octet-stream")
```

---

## 4. Test Configuration Updates

### A. Update `run_tests.py`
Change the imported backend server from the mock backend to the real backend so that tests execute against the SQLite application:
- **Before**: `from secure_space_app.tests.mock_backend import app`
- **After**: `from secure_space_app.backend.app.main import app`

### B. Update `test_infra_check.py`
In `test_infra_check.py`, the server is started unconditionally. It should check if the port is already in use (e.g. by `run_tests.py`) before attempting to bind to port 8089 to prevent socket errors.
Add `is_port_in_use` helper:
```python
def is_port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex((host, port)) == 0
```
Update `setUpClass` in `test_infra_check.py` to check for active port.

---

## 5. Recommended Code Modifications for Worker

The worker should apply the following modifications:

### 1. File: `secure_space_app/backend/app/main.py`
Replace the implementation of `/api/files/download/{file_id}` (lines 465-504) with the database-first query order to fix the `test_download_non_existent_file` failure.

### 2. File: `secure_space_app/tests/run_tests.py`
Update the `app` import statement on line 11 to import `app` from `secure_space_app.backend.app.main` and adjust log strings from "Mock backend" to "Real database-backed backend".

### 3. File: `secure_space_app/tests/test_infra_check.py`
Introduce `is_port_in_use` detection in `setUpClass` to match the robust setup logic of `test_e2e_suite.py`.
