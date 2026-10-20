# Document Management API

A RESTful API for uploading, listing, retrieving, and deleting documents, built with **FastAPI**, backed by **MinIO** for object storage and **SQLite** (or any SQLAlchemy-compatible DB) for metadata persistence.

---

## Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Getting Started](#getting-started)
  - [1. Clone the repository](#1-clone-the-repository)
  - [2. Start MinIO with Docker](#2-start-minio-with-docker)
  - [3. Configure environment variables](#3-configure-environment-variables)
  - [4. Install dependencies](#4-install-dependencies)
  - [5. Run the API](#5-run-the-api)
- [API Reference](#api-reference)
- [File Validation](#file-validation)
- [Configuration Reference](#configuration-reference)
- [Running Tests](#running-tests)

---

## Features

- 📤 **Upload** documents with file-type and magic-byte validation
- 📋 **List** all uploaded documents (newest first)
- 🔍 **Retrieve** document metadata by ID
- 🔗 **Generate** time-limited pre-signed download URLs via MinIO
- 🗑️ **Delete** documents from both storage and the metadata database
- 🛡️ Atomic operations — storage and DB are kept consistent on failures

---

## Tech Stack

| Layer            | Technology                          |
|------------------|-------------------------------------|
| API Framework    | [FastAPI](https://fastapi.tiangolo.com/) |
| Object Storage   | [MinIO](https://min.io/)            |
| Database ORM     | [SQLAlchemy](https://www.sqlalchemy.org/) |
| Settings         | [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) |
| ASGI Server      | [Uvicorn](https://www.uvicorn.org/) |
| Testing          | [pytest](https://pytest.org/) + [HTTPX](https://www.python-httpx.org/) |

---

## Project Structure

```
minio_assingment/
├── app/
│   ├── __init__.py       # Package marker
│   ├── config.py         # Settings loaded from .env
│   ├── database.py       # SQLAlchemy engine & session
│   ├── main.py           # FastAPI app, routes, lifespan
│   ├── models.py         # Document ORM model
│   ├── schemas.py        # Pydantic request/response schemas
│   └── storage.py        # MinIO client & helper functions
├── tests/
│   └── test_document.py  # Pytest test suite
├── docker-compose.yml    # MinIO service definition
├── requirements.txt      # Python dependencies
├── .env                  # Local environment variables (not committed)
└── README.md
```

---

## Prerequisites

- Python 3.10+
- [Docker](https://www.docker.com/) (for running MinIO locally)

---

## Getting Started

### 1. Clone the repository

```bash
git clone <repo-url>
cd minio_assingment
```

### 2. Start MinIO with Docker

```bash
docker-compose up -d
```

This starts:
- **MinIO API** on `http://localhost:9000`
- **MinIO Console** (web UI) on `http://localhost:9001`

### 3. Configure environment variables

Copy the example below into a `.env` file at the project root and fill in your values:

```env
# MinIO server credentials (used by Docker)
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# Application connection settings
# IMPORTANT: MINIO_SECRET_KEY must match MINIO_ROOT_PASSWORD
MINIO_ENDPOINT=127.0.0.1:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin        
MINIO_BUCKET=documents
MINIO_SECURE=false

# Database
DATABASE_URL=sqlite:///./documents.db

# Upload limits
MAX_FILE_SIZE_MB=10
PRESIGNED_URL_EXPIRY_SECONDS=300
```

> [!CAUTION]
> `MINIO_SECRET_KEY` **must** match `MINIO_ROOT_PASSWORD`. A mismatch causes a `SignatureDoesNotMatch` S3 error on startup.

### 4. Install dependencies

```bash
# Create and activate a virtual environment (recommended)
python -m venv dma
dma\Scripts\activate        # Windows
# source dma/bin/activate   # macOS / Linux

pip install -r requirements.txt
```

### 5. Run the API

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`.  
Interactive docs: `http://127.0.0.1:8000/docs`

---

## API Reference

### `GET /`
Health check — confirms the API is running.

**Response `200`**
```json
{ "message": "Document Management API is running" }
```

---

### `POST /documents`
Upload a new document.

**Request** — `multipart/form-data`

| Field | Type | Description         |
|-------|------|---------------------|
| `file` | file | The file to upload  |

**Response `201`**
```json
{
  "id": 1,
  "filename": "report.pdf",
  "content_type": "application/pdf",
  "size": 204800,
  "upload_date": "2026-10-20T04:00:00Z",
  "object_key": "a3f1c2d4e5b6...pdf"
}
```

**Error codes**

| Code | Reason |
|------|--------|
| `400` | Unsupported extension, content type, empty file, magic-byte mismatch, or non-UTF-8 text file |
| `413` | File exceeds `MAX_FILE_SIZE_MB` |
| `503` | MinIO storage error |

---

### `GET /documents`
List all uploaded documents, newest first.

**Response `200`** — array of document objects (same shape as upload response).

---

### `GET /documents/{document_id}`
Retrieve metadata for a single document.

**Response `200`** — document object.  
**Response `404`** — document not found.

---

### `GET /documents/{document_id}/download`
Get a pre-signed download URL valid for `PRESIGNED_URL_EXPIRY_SECONDS` seconds.

**Response `200`**
```json
{
  "download_url": "http://127.0.0.1:9000/documents/a3f1...pdf?X-Amz-Signature=...",
  "expires_in_seconds": 300
}
```

**Response `404`** — document not found.  
**Response `503`** — MinIO error.

---

### `DELETE /documents/{document_id}`
Delete a document from both MinIO and the database.

**Response `200`**
```json
{ "message": "Document deleted successfully" }
```

**Response `404`** — document not found.  
**Response `503`** — MinIO deletion failed (metadata is preserved).

---

## File Validation

Uploads are rejected unless they pass **all** of the following checks:

| Check | Allowed values |
|-------|----------------|
| File extension | `.pdf`, `.jpg`, `.jpeg`, `.png`, `.txt` |
| MIME / content type | `application/pdf`, `image/jpeg`, `image/png`, `text/plain` |
| Magic bytes | PDF (`%PDF-`), PNG (`\x89PNG`), JPEG (`\xff\xd8\xff`) |
| Encoding (`.txt` only) | Must be valid UTF-8 |
| File size | ≤ `MAX_FILE_SIZE_MB` (default 10 MB) |

---

## Configuration Reference

All settings are read from the `.env` file via `pydantic-settings`.

| Variable | Default | Description |
|----------|---------|-------------|
| `MINIO_ENDPOINT` | `127.0.0.1:9000` | MinIO host and port |
| `MINIO_ACCESS_KEY` | *(required)* | MinIO access key / root user |
| `MINIO_SECRET_KEY` | *(required)* | MinIO secret key / root password |
| `MINIO_BUCKET` | `documents` | Bucket name (auto-created on startup) |
| `MINIO_SECURE` | `false` | Use TLS (`true`) or plain HTTP (`false`) |
| `DATABASE_URL` | `sqlite:///./documents.db` | SQLAlchemy database URL |
| `MAX_FILE_SIZE_MB` | `10` | Maximum upload size in megabytes |
| `PRESIGNED_URL_EXPIRY_SECONDS` | `300` | Pre-signed URL lifetime in seconds |

---

## Running Tests

The test suite uses an **in-memory SQLite** database and stubs out all MinIO calls — no running services are required.

```bash
pytest tests/ -v
```

**Test coverage includes:**
- `GET /` health check
- Upload and list workflow (`POST /documents`, `GET /documents`)
- Rejection of unsupported file extensions
- 404 handling for unknown document IDs

