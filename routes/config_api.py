from fastapi import APIRouter, HTTPException
from database.schema import TafsiriResponsesBaseSchema

router = APIRouter()


@router.post('/new_config', response_model=TafsiriResponsesBaseSchema)
async def create_new_config(config: TafsiriResponsesBaseSchema):
    """
      _Create a new configuration for the Tafsiri API
    """



@router.get('/get_config', response_model=TafsiriResponsesBaseSchema)
async def get_config():
    """
      _Get the configuration for the Tafsiri API
    """
    pass


@router.put('/update_config', response_model=TafsiriResponsesBaseSchema)
async def update_config():
    """
      _Update the configuration for the Tafsiri API
    """
    pass


@router.delete('/delete_config', response_model=TafsiriResponsesBaseSchema)
async def delete_config():
    """
      _Delete the configuration for the Tafsiri API
    """
    pass
