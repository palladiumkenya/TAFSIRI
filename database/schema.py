from typing import Optional
import uuid
from pydantic import BaseModel
from datetime import datetime


class TafsiriResponsesBaseSchema(BaseModel):
    question: str
    response: Optional[str] = None
    response_rating: Optional[int] = None
    response_rating_comment: Optional[str] = None
    time_taken_mms: float
    created_at: datetime = datetime.now()
    created_by: Optional[str] = None
    is_valid: bool = True

    class Config:
        extra = 'allow'
        orm_mode = True


class TafsiriConfigSchema(BaseModel):
    configID: int = uuid.uuid4()
    tables: list
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    example_prompt: str

    class Config:
        extra = 'allow'
        orm_mode = True
