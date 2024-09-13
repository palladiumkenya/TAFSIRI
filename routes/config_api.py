from fastapi import APIRouter, HTTPException, Depends
from database.schema import TafsiriConfigSchema
from bson.objectid import ObjectId
from database.database import get_mongo_collection

router = APIRouter()

# Collection name
configs = "tafsiri_configs"


def format_mongo_obj(obj):
    """
    Helper function to format MongoDB object
    """
    obj["_id"] = str(obj["_id"])
    return obj


@router.get("/get_configs", response_model=list[TafsiriConfigSchema])
async def get_configs(collection=Depends(lambda: get_mongo_collection(configs))):
    """
    Get all configurations for the Tafsiri API
    """
    config_data = collection.find()
    return [format_mongo_obj(config) for config in config_data]


@router.post("/new_config", response_model=TafsiriConfigSchema)
async def create_new_config(config: TafsiriConfigSchema, collection=Depends(lambda: get_mongo_collection(configs))):
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
async def get_config(config_id):
    """
    Get a specific configuration for the Tafsiri API
    """
    collection = get_mongo_collection(configs)
    if collection is None:
        raise HTTPException(status_code=500, detail="Collection not found")
    try:
        config_id = ObjectId(config_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid config ID format")

    config = collection.find_one({"_id": config_id})
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    # Convert ObjectId to string
    config["_id"] = str(config["_id"])

    return config


@router.put("/update_config/{config_id}", response_model=TafsiriConfigSchema)
async def update_config(config_id, config):
    """
    Update a specific configuration for the Tafsiri API
    """
    collection = get_mongo_collection(configs)
    if collection is None:
        raise HTTPException(status_code=500, detail="Collection not found")
    config_data = config.model_dump(exclude_unset=True)
    result = collection.update_one({"_id": config_id}, {"$set": config_data})
    if result.modified_count == 1:
        return format_mongo_obj(config_data)
    raise HTTPException(status_code=404, detail="Config not found")


@router.delete("/delete_config/{config_id}")
async def delete_config(config_id):
    """
    Delete a specific configuration for the Tafsiri API
    """
    collection = get_mongo_collection(configs)
    if collection is None:
        raise HTTPException(status_code=500, detail="Collection not found")
    try:
        config_id = ObjectId(config_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid config ID format")
    result = collection.delete_one({"_id": config_id})
    if result.deleted_count == 1:
        return {"message": "Config deleted successfully"}
    raise HTTPException(status_code=404, detail="Config not found")
