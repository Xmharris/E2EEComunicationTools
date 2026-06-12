# Workspace & Environment Investigation Report

## Executive Summary
This report summarizes the environment investigation for the E2EE Secure Space Application. Key findings show that Python 3.9.13 is available with core dependencies `fastapi`, `uvicorn`, and `cryptography` installed, though `sqlalchemy`, `pycryptodome`, and `pytest` are missing. Android development components (JDK, Gradle, Kotlin, Android CLI) are completely absent. The workspace contains initial mock E2E test files under `secure_space_app/tests/`, and we propose a robust directory layout for `secure_space_app/backend` and `secure_space_app/client`.

---

## 1. Python Environment & Packages

### Python Version
* **Python version**: `3.9.13`
* **Path status**: Globally available via system PATH.

### Package Status
The following table details the status of requested packages:

| Package | Status | Version | Notes |
|---|---|---|---|
| **fastapi** | Installed | `0.128.8` | Available for backend implementation |
| **uvicorn** | Installed | `0.39.0` | Available for backend serving |
| **cryptography** | Installed | `48.0.1` | Used in `client_sim.py` for client-side crypto |
| **sqlalchemy** | **Missing** | N/A | Needs to be installed for database ORM |
| **pycryptodome** | **Missing** | N/A | Needs to be installed if required, though `cryptography` is already present |
| **pytest** | **Missing** | N/A | Tests are currently executed using built-in `unittest` module |

### Test Suite Execution
* Because `pytest` is missing, tests are run with Python's built-in `unittest` module.
* **Sanity check (`test_infra_check.py`)**: Ran 1 test, completed successfully.
* **E2E suite (`test_e2e_suite.py`)**: Ran 60 tests, but failed with **1 failure** and **6 errors**. Key errors include:
  1. `ValueError: Public key for user 'eve' not found on backend.` in `test_add_non_existent_user_to_space` and `test_send_dm_to_non_existent_user`.
  2. `ValueError: No key for space space1 found locally` in unauthorized scheduling and file sharing.
  3. `AttributeError: 'str' object has no attribute 'hex'` on encrypted file keys.
  4. `cryptography.exceptions.InvalidTag` during eavesdropping prevention test.
  5. DM payload content assertion failures.

---

## 2. JDK, Gradle, and Android Environment

The Android build and compilation tools are **not installed** or configured globally.

* **JDK/Java**: `java` is not recognized (CommandNotFoundException). No `JAVA_HOME` environment variable exists.
* **Gradle**: `gradle` is not recognized. No `GRADLE_HOME` exists.
* **Kotlin Compiler**: `kotlinc` is not recognized.
* **Android CLI**: `android` is not recognized.

### Recommendations:
1. Install **JDK 17 or higher** (required for modern Android projects).
2. Install the **Android SDK** and tools.
3. Establish a **Gradle wrapper (`gradlew` / `gradlew.bat`)** in the root of the client project. Using the Gradle wrapper ensures the correct Gradle version is downloaded and used dynamically without needing a global Gradle install on developer systems.

---

## 3. Existing Files & Directories

The workspace directory (`C:\Users\xavie\Documents\antigravity\quick-franklin`) contains:

1. **`.git/`**: Git metadata.
2. **`.agents/`**: Agent progress and orchestration files (sentinel, orchestrator, sub_orch_impl_m1, sub_orch_e2e_testing, worker_m1, teamwork_preview_explorer_m1_1).
3. **`secure_space_app/`**: Base package containing:
   * `secure_space_app/__init__.py`
   * `secure_space_app/tests/` (E2E simulation harness, implemented by `worker_m1`):
     * `secure_space_app/tests/__init__.py`
     * `secure_space_app/tests/client_sim.py` (implements client-side cryptographic functions & HTTP actions)
     * `secure_space_app/tests/mock_backend.py` (in-memory FastAPI mock endpoint mapping)
     * `secure_space_app/tests/test_infra_check.py` (verifies fundamental flow)
     * `secure_space_app/tests/test_e2e_suite.py` (comprehensive 60-test E2E suite)

---

## 4. Proposed Layout for Backend and Client

### A. Backend Structure (`secure_space_app/backend`)
We recommend a modular FastAPI layout with SQLite database integration:

```text
secure_space_app/backend/
├── app/
│   ├── __init__.py
│   ├── main.py            # Entrypoint: FastAPI app, lifespan setup, router inclusion
│   ├── database.py        # SQLite database engine, session local, declarative base
│   ├── models.py          # SQLAlchemy models (User, Space, Message, SpaceKeyExchange, File)
│   ├── schemas.py         # Pydantic schemas (UserRegister, SpaceCreate, MessageSend, etc.)
│   ├── crud.py            # SQLite CRUD query functions
│   ├── config.py          # App settings (database URL, encrypted file storage path)
│   └── storage.py         # Handles physical upload/download of encrypted binary files
├── tests/
│   ├── __init__.py
│   └── test_backend.py    # Unit tests specifically for backend endpoints and validation
└── requirements.txt       # Dependencies (fastapi, uvicorn, sqlalchemy, cryptography, pydantic)
```

### B. Client Structure (`secure_space_app/client`)
We recommend a standard Gradle-based Android structure configured for Room database caching and clean cryptography:

```text
secure_space_app/client/
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
├── build.gradle.kts       # Root-level build configuration (plugins definition)
├── settings.gradle.kts     # Project name and module definitions (:app)
├── gradle.properties       # JVM parameters and AndroidX options
├── gradlew                 # Linux/macOS wrapper script
├── gradlew.bat             # Windows wrapper script
└── app/
    ├── build.gradle.kts   # App-level build config (Room, Retrofit, AndroidX dependencies)
    ├── src/
    │   ├── main/
    │   │   ├── AndroidManifest.xml
    │   │   ├── java/com/secure/space/
    │   │   │   ├── crypto/
    │   │   │   │   └── CryptoEngine.kt  # ECDH keygen, HKDF, AES-GCM (256-bit) wrapper, PBKDF2
    │   │   │   ├── api/
    │   │   │   │   ├── SecureSpaceApi.kt # Retrofit REST API endpoints definition
    │   │   │   │   └── NetworkClient.kt  # Handles HTTP calls, headers, and interceptors
    │   │   │   ├── model/
    │   │   │   │   ├── User.kt
    │   │   │   │   ├── Message.kt
    │   │   │   │   ├── Space.kt
    │   │   │   │   └── Meeting.kt
    │   │   │   ├── db/
    │   │   │   │   ├── AppDatabase.kt    # Room database entry point
    │   │   │   │   ├── UserDao.kt
    │   │   │   │   ├── MessageDao.kt
    │   │   │   │   └── SpaceDao.kt
    │   │   │   └── MainActivity.kt       # Application entry point/activity
    │   │   └── res/                          # Layout files, strings, colors, drawable resources
    │   └── test/
    │       └── java/com/secure/space/        # Local JVM unit tests using JUnit and Robolectric
```
