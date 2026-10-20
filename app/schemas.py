from datetime import datetime

from pydantic import BaseModel, ConfigDict


class DocumentResponse(BaseModel):
    id: int
    filename: str
    content_type: str
    size: int
    upload_date: datetime
    object_key: str

    model_config = ConfigDict(from_attributes=True)


class DownloadResponse(BaseModel):
    download_url: str
    expires_in_seconds: int