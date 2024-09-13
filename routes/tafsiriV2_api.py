import functools
import os
import requests
import time
import logging

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import Table, text
from llama_index.core import VectorStoreIndex
from llama_index.core.objects import (
    ObjectIndex,
    SQLTableNodeMapping,
    SQLTableSchema,
)
from llama_index.llms.openai import OpenAI
from llama_index.legacy import SQLDatabase

from database.schema import TafsiriResponsesBaseSchema
from settings import settings
from database.database import engine, SessionLocal, get_mongo_collection, metadata, TafsiriResp, CONFIGS_COLLECTION

# Set up logging
log = logging.getLogger()
log.setLevel('DEBUG')
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter(
    "%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
log.addHandler(handler)

router = APIRouter()


# OpenAI setup
os.environ["OPENAI_API_KEY"] = settings.OPENAI_KEY
llm = OpenAI(temperature=0, model="gpt-4o")

# Database setup
# tables = []

CACHE_TIMEOUT = 3600  # 1 hour


def get_dictionary_info(tables, config_om_host, config_jwt_token):
    # JWT and host for fetching table descriptions
    jwt_token = config_jwt_token
    om_host = config_om_host

    # Fetch table descriptions and metadata
    tables_info = []
    for table_name in tables:
        table_description = ""
        columns_info = {}
        table_glossary_uri = f"{om_host}/api/v1/glossaryTerms/name/text2sql.{table_name}"
        try:
            response = requests.get(table_glossary_uri, headers={
                                    "Authorization": f"Bearer {jwt_token}"}, verify=False)
            response.raise_for_status()

            if response.status_code // 100 == 2:
                glossary_term = response.json()
                table_description = glossary_term.get("description")
                if table_description is not None:
                    # Get column descriptions dynamically from the MSSQL table
                    table = Table(table_name, metadata, autoload=True)
                    columns = table.columns.keys()
                    columns_info_list = []
                    for column_name in columns:
                        column_glossary_uri = f"{om_host}/api/v1/glossaryTerms/name/text2sql.{table_name}.{column_name}"
                        try:
                            response = requests.get(column_glossary_uri,
                                                    headers={"Authorization": f"Bearer {jwt_token}"})
                            response.raise_for_status()

                            if response.status_code // 100 == 2:
                                column_info = response.json()
                                column_desc = f"\"{column_name}\": {column_info.get('description')}"
                                columns_info_list.append(column_desc)
                        except requests.exceptions.HTTPError as he:
                            if he.response.status_code // 100 == 4:
                                print(
                                    f"Glossary term not found for URI: {column_glossary_uri}")
                            else:
                                print(
                                    f"Failed to retrieve column description for {column_name} with message {he.response.text}",
                                    he)
                    columns_info = ". ".join(columns_info_list)
        except requests.exceptions.HTTPError as he:
            if he.response.status_code // 100 == 4:
                print(f"Glossary term not found for URI: {table_glossary_uri}")
            else:
                print(
                    f"Failed to retrieve table description for {table_name} with message {he.response.text}", he)

        tables_info.append(SQLTableSchema(
            table_name=table_name,
            context_str=(
                f'description of the table: {table_description}. These are columns in the table and their descriptions: {columns_info}')
        ))

    return tables_info


# Step 3: Determine if the question requires the use of the second table
def is_join_required(first_table_name):
    return first_table_name in ["Linelist_FACTART", "LineListTransHTS", "LineListTransPNS", "LinelistHTSEligibilty"]


@functools.lru_cache(maxsize=None)
def get_dictionary_info_cached(tables, om_host, jwt_token):
    """
    Get table descriptions from the OM API and cache the results
    """
    return get_dictionary_info(tables, om_host, jwt_token)


# Endpoint to retrieve data based on natural language query
class NaturalLanguageQuery(BaseModel):
    question: str
    user_id: str
    config_id: str


@router.post('/question')
async def query_from_natural_language(nl_query: NaturalLanguageQuery):
    """
    Endpoint to retrieve data based on natural language query from user
    """
    start_time = time.time()
    question = nl_query.question
    # user_id = nl_query.user_id
    config_id = nl_query.config_id

    # Fetch configuration details
    collection = get_mongo_collection(CONFIGS_COLLECTION)
    config_id_obj = ObjectId(config_id)
    config = collection.find_one({"_id": config_id_obj})
    if config is None:
        raise HTTPException(status_code=404, detail="Config not found")

    # Set up SQL database
    tables = config["tables"]

    # Get OM host and JWT
    om_host = config["om_host"]
    jwt_token = config["om_jwt"]

    try:
        # store schema information for each table.
        table_schema_objs = get_dictionary_info_cached(
            tuple(tables), om_host, jwt_token)
        # Create SQL database
        sql_database = SQLDatabase(engine, include_tables=tables)
        table_node_mapping = SQLTableNodeMapping(sql_database)

        obj_index = ObjectIndex.from_objects(
            table_schema_objs,
            table_node_mapping,
            VectorStoreIndex,
        )

    # Get custom prompt from config
        custom_txt2sql_prompt = config["example_prompt"]

        from llama_index.core.retrievers import NLSQLRetriever

        # default retrieval (return_raw=True)
        nl_sql_retriever = NLSQLRetriever(
            sql_database,
        )

        # Retrieve objects dynamically with a maximum similarity_top_k value of 2
        retriever = obj_index.as_retriever(similarity_top_k=2)
        retrieved_objs = retriever.retrieve(question)

        first_identified_table = retrieved_objs[0]
        second_identified_table = retrieved_objs[1]

        print("First Identified Table:", first_identified_table)
        print("Second Identified Table:", second_identified_table)

        custom_prompt_1 = (
            "Please calculate proportion when asked to, generate sql query that contains both the numbers and proportion. Only output sql query, do not attempt to generate an answer"
            f"You can refer to {custom_txt2sql_prompt} for examples and instructions on how to generate a SQL statement."
            f"Write a SQL query to answer the following question: {question}, Using the table {first_identified_table}."
            "Please take note of the column names which are in quotes and their description."
        )
        custom_prompt_2 = (
            "Please calculate proportion when asked to, generate sql query that contains both the numbers and proportion. Only output sql query, do not attempt to generate an answer"
            f"You can refer to {custom_txt2sql_prompt} for examples and instructions on how to generate a SQL statement. "
            f"Write a SQL query to answer the following question: {question}, using the table {first_identified_table}. "
            "Please take note of the column names which are in quotes and their description. Do not use the two tables if you are not merging, be careful to differentiate which column names are in which table."
            f"If the question requires joining or merging, join with {second_identified_table} to retrieve the required variables."
        )

        first_table_name = first_identified_table.table_name
        print(first_table_name)

        # Check if the join is required
        if is_join_required(first_table_name):
            custom_prompt = custom_prompt_2
            print("custom prompt 2 was used")
        else:
            custom_prompt = custom_prompt_1
            print("custom prompt 1 was used")

        # Generate SQL query
        response = nl_sql_retriever.retrieve_with_metadata(custom_prompt)
        response_list, metadata_dict = response
        print(metadata_dict["sql_query"])

        sql_query = metadata_dict["sql_query"]
        log.debug(f"Generated SQL query: {sql_query}")
        with SessionLocal() as session:
            result = session.execute(text(sql_query))
            rows = result.fetchall()
            # Get column names
            columns = result.keys()

            data = [dict(zip(columns, row)) for row in rows]
        end_time = time.time()  # Record the end time
        time_taken = end_time - start_time  # Calculate the time taken
        # Save metrics for analytics
        response_data = {
            "question": question,
            "response": sql_query,
            "time_taken_mms": time_taken,
            "created_at": datetime.now(),
        }
        validated_data = TafsiriResponsesBaseSchema(
            **response_data
        )
        saved_response = TafsiriResp.insert_one(validated_data.dict())

        return {"sql_query": sql_query, "data": data, "time_taken": time_taken, "saved_response_id": str(saved_response.inserted_id)}
    except Exception as e:
        log.error(f"Error processing query: {e}")
        # Save metrics for analytics
        response_data = {
            "question": question,
            "response": sql_query,
            "time_taken_mms": 0,
            "created_at": datetime.now(),
            "is_valid": False
        }
        validated_data = TafsiriResponsesBaseSchema(
            **response_data
        )
        saved_response = TafsiriResp.insert_one(validated_data.dict())
        return {"sql_query": sql_query or None, "data": [], "time_taken": 0, "saved_response_id": str(saved_response.inserted_id)}


# TODO: Implement the feedbck endpoints
# class NaturalLanguageResponseRating(BaseModel):
#     response_rating: int
#     response_rating_comment: str | None = None


# @router.post('/rate/{response_id}')
# async def rate_response(rating: NaturalLanguageResponseRating, response_id: str):
#     try:
#         response_id_obj = ObjectId(response_id)
#     except Exception as e:
#         raise HTTPException(
#             status_code=400, detail="Invalid response_id") from e

#     TafsiriResp.update_one(
#         {"_id": response_id_obj},
#         {"$set": {"response_rating": rating.response_rating,
#                   "response_rating_comment": rating.response_rating_comment}}
#     )

#     return {"success": True}


# TODO: Implement the Table description endpoint
# Endpoint to retrieve table descriptions
# @router.get('/table_descriptions')
# async def get_table_descriptions():
#     try:
#         tables_info = get_dictionary_info_cached()
#         descriptions = [
#             {"table_name": table.table_name, "description": table.context_str}
#             for table in tables_info
#         ]
#         return {"tables": descriptions}
#     except Exception as e:
#         log.error(f"Error retrieving table descriptions: {e}")
#         raise HTTPException(status_code=500, detail=str(e)) from e
