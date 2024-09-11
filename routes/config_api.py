from fastapi import APIRouter, HTTPException, Depends
from pymongo.collection import Collection
from database import get_mongo_collection
from database.schema import TafsiriConfigSchema
from bson.objectid import ObjectId

from settings import settings

router = APIRouter()

# Collection name
configs = "tafsiri_configs"

# Helper function to format MongoDB object
def format_mongo_obj(obj):
    obj["_id"] = str(obj["_id"])
    return obj


@router.get("/get_configs", response_model=list[TafsiriConfigSchema])
async def get_configs(collection: Collection = Depends(get_mongo_collection(configs))):
    """
    Get all configurations for the Tafsiri API
    """
    config_data = collection.find()
    return [format_mongo_obj(config) for config in config_data]


@router.post("/new_config", response_model=TafsiriConfigSchema)
async def create_new_config(config: TafsiriConfigSchema, collection: Collection = Depends(get_mongo_collection(configs))):
    """
    Create a new configuration for the Tafsiri API
    """
    config_data = config.model_dump(exclude_unset=True)
    result = collection.insert_one(config_data)
    if result.inserted_id:
        return format_mongo_obj(config_data)
    raise HTTPException(
        status_code=400, detail="Configuration could not be created")


@router.get("/get_config/{config_id}", response_model=TafsiriConfigSchema)
async def get_config(config_id: str, collection: Collection = Depends(get_mongo_collection(configs))):
    """
    Get the configuration for the Tafsiri API by ID
    """
    config_data = collection.find_one({"_id": ObjectId(config_id)})
    if config_data:
        return format_mongo_obj(config_data)
    raise HTTPException(status_code=404, detail="Configuration not found")


@router.put("/update_config/{config_id}", response_model=TafsiriConfigSchema)
async def update_config(config_id: str, updated_config: TafsiriConfigSchema, collection: Collection = Depends(get_mongo_collection(configs))):
    """
    Update the configuration for the Tafsiri API by ID
    """
    updated_data = updated_config.dict(exclude_unset=True)
    result = collection.update_one(
        {"_id": ObjectId(config_id)}, {"$set": updated_data})
    if result.modified_count:
        return format_mongo_obj(collection.find_one({"_id": ObjectId(config_id)}))
    raise HTTPException(
        status_code=400, detail="Configuration could not be updated")


@router.delete("/delete_config/{config_id}", response_model=TafsiriConfigSchema)
async def delete_config(config_id: str, collection: Collection = Depends(get_mongo_collection(configs))):
    """
    Delete the configuration for the Tafsiri API by ID
    """
    result = collection.delete_one({"_id": ObjectId(config_id)})
    if result.deleted_count:
        return {"detail": "Configuration deleted successfully"}
    raise HTTPException(status_code=404, detail="Configuration not found")
