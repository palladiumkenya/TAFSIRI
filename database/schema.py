from typing import Optional
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
