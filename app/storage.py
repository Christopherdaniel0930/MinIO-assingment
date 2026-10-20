from datetime import timedelta

from minio import Minio

from app.config import settings


client = Minio(
    settings.minio_endpoint,
    access_key=settings.minio_access_key,
    secret_key=settings.minio_secret_key,
    secure=settings.minio_secure,
)


def ensure_bucket_exists():
    if not client.bucket_exists(settings.minio_bucket):
        client.make_bucket(settings.minio_bucket)


def upload_object(
    object_key: str,
    file_data,
    size: int,
    content_type: str,
):
    client.put_object(
        bucket_name=settings.minio_bucket,
        object_name=object_key,
        data=file_data,
        length=size,
        content_type=content_type,
    )


def generate_download_url(object_key: str) -> str:
    return client.presigned_get_object(
        settings.minio_bucket,
        object_key,
        expires=timedelta(
            seconds=settings.presigned_url_expiry_seconds
        ),
    )


def delete_object(object_key: str):
    client.remove_object(
        settings.minio_bucket,
        object_key,
    )
