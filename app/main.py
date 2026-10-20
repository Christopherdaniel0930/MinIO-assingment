import io
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from minio.error import S3Error
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from app.config import settings
from app.database import Base, engine, get_db
from app.models import Document
from app.schemas import DocumentResponse, DownloadResponse
from app.storage import (
    client,
    delete_object,
    ensure_bucket_exists,
    generate_download_url,
    upload_object,
)


ALLOWED_TYPES = {
    "application/pdf",
    "image/jpeg",
    "image/png",
    "text/plain",
}

ALLOWED_EXTENSIONS = {
    ".pdf",
    ".jpg",
    ".jpeg",
    ".png",
    ".txt",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    ensure_bucket_exists()
    yield


app = FastAPI(
    title="Document Management API",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
def home():
    return {"message": "Document Management API is running"}


@app.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=201,
)
def upload_document(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = Path(file.filename or "").name
    extension = Path(filename).suffix.lower()
    content_type = file.content_type or ""

    if not filename or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file extension",
        )

    if content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported content type",
        )

    max_size = settings.max_file_size_mb * 1024 * 1024

    try:
        data = file.file.read(max_size + 1)

        if not data:
            raise HTTPException(
                status_code=400,
                detail="Uploaded file is empty",
            )

        if len(data) > max_size:
            raise HTTPException(
                status_code=413,
                detail="File exceeds the maximum allowed size",
            )

        # Check common file signatures instead of trusting
        # the client-provided content type alone.
        signatures = {
            ".pdf": lambda b: b.startswith(b"%PDF-"),
            ".png": lambda b: b.startswith(b"\x89PNG\r\n\x1a\n"),
            ".jpg": lambda b: b.startswith(b"\xff\xd8\xff"),
            ".jpeg": lambda b: b.startswith(b"\xff\xd8\xff"),
        }

        check_signature = signatures.get(extension)

        if check_signature and not check_signature(data):
            raise HTTPException(
                status_code=400,
                detail="File content does not match its extension",
            )

        if extension == ".txt":
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                raise HTTPException(
                    status_code=400,
                    detail="Text file must use UTF-8 encoding",
                )

        object_key = f"{uuid.uuid4().hex}{extension}"

        upload_object(
            object_key=object_key,
            file_data=io.BytesIO(data),
            size=len(data),
            content_type=content_type,
        )

        document = Document(
            filename=filename,
            content_type=content_type,
            size=len(data),
            upload_date=datetime.now(timezone.utc),
            object_key=object_key,
        )

        try:
            db.add(document)
            db.commit()
            db.refresh(document)
        except SQLAlchemyError:
            db.rollback()
            try:
                delete_object(object_key)
            except S3Error:
                pass
            raise

        return document

    except HTTPException:
        raise
    except S3Error as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Object storage operation failed",
        ) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not save document metadata",
        ) from exc


@app.get("/documents", response_model=list[DocumentResponse])
def list_documents(db: Session = Depends(get_db)):
    return (
        db.query(Document)
        .order_by(Document.id.desc())
        .all()
    )


@app.get(
    "/documents/{document_id}",
    response_model = DocumentResponse,
)
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return document


@app.get(
    "/documents/{document_id}/download",
    response_model=DownloadResponse,
)
def get_download_url(
    document_id: int,
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    try:
        url = generate_download_url(document.object_key)
    except S3Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not generate download URL",
        ) from exc

    return DownloadResponse(
        download_url=url,
        expires_in_seconds=settings.presigned_url_expiry_seconds,
    )


@app.delete("/documents/{document_id}")
def remove_document(
    document_id: int,
    db: Session = Depends(get_db),
):
    document = db.get(Document, document_id)

    if document is None:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    try:
        # Delete the object first. If that fails, retain metadata.
        client.remove_object(
            settings.minio_bucket,
            document.object_key,
        )
    except S3Error as exc:
        raise HTTPException(
            status_code=503,
            detail="Could not delete file from object storage",
        ) from exc

    try:
        db.delete(document)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=(
                "File was deleted from storage, but metadata "
                "could not be deleted"
            ),
        ) from exc

    return {"message": "Document deleted successfully"}