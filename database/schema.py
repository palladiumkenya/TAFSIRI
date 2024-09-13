from typing import List, Optional
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
    config_name: Optional[str] = None
    tables: Optional[List[str]] = None
    db_host: Optional[str] = None
    db_port: Optional[int] = None
    db_user: Optional[str] = None
    db_password: Optional[str] = None
    db_name: Optional[str] = None
    example_prompt: Optional[str] = None
    om_host: Optional[str] = None
    om_jwt: Optional[str] = None

    class Config:
        extra = 'allow'
        orm_mode = True
