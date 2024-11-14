import csv
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
from database.database import engine, SessionLocal, metadata, client, TafsiriResp

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
tables = ["Linelist_FACTART", "LineListTransHTS", "LinelistPrep", "LinelistPrepAssessments", "LinelistHEI",
          "LinelistHTSEligibilty", "LineListOVCEligibilityAndEnrollments", "LineListOTZEligibilityAndEnrollments",
          "LineListPBFW", "LineListTransPNS"]
sql_database = SQLDatabase(engine, include_tables=tables)
CACHE_TIMEOUT = 3600  # 1 hour


def get_dictionary_info():
    csv_path = 'dictionary/text2sql.csv'

    table_descriptions = {}

    with open(csv_path, mode='r') as file:
        reader = csv.DictReader(file)

        for row in reader:
            parent_value = row['parent'].replace('text2sql.', '') if row['parent'] else None
            if parent_value in tables or row['name'] in tables:
                if not parent_value:
                    table_name = row['name']
                    table_description = row['description']
                    table_descriptions[table_name] = {
                        'description': table_description,
                        'columns': {}
                    }
                else:
                    table_name, column_name = parent_value, row['name']
                    column_description = row['description']

                    if table_name in table_descriptions:
                        table_descriptions[table_name]['columns'][column_name] = column_description

    tables_info = []
    for table_name, data in table_descriptions.items():
        table_description = data['description']
        columns_info_list = [
            f'"{col_name}": {col_desc}' for col_name, col_desc in data['columns'].items()
        ]
        columns_info = ". ".join(columns_info_list)

        tables_info.append(
            SQLTableSchema(
                table_name=table_name,
                context_str=(
                    f'description of the table: {table_description}. '
                    f'These are columns in the table and their descriptions: {columns_info}'
                )
            )
        )
    return tables_info


# Step 3: Determine if the question requires the use of the second table
def is_join_required(first_table_name):
    return first_table_name in ["Linelist_FACTART", "LineListTransHTS", "LineListTransPNS", "LinelistHTSEligibilty"]


@functools.lru_cache(maxsize=None)
def get_dictionary_info_cached():
    return get_dictionary_info()


# Endpoint to retrieve data based on natural language query
class NaturalLanguageQuery(BaseModel):
    question: str
    user_id: str


@router.post('/query_from_natural_language')
async def query_from_natural_language(nl_query: NaturalLanguageQuery):
    start_time = time.time()
    question = nl_query.question
    user_id = nl_query.user_id
    try:
        # store schema information for each table.
        table_schema_objs = get_dictionary_info_cached()
        table_node_mapping = SQLTableNodeMapping(sql_database)

        obj_index = ObjectIndex.from_objects(
            table_schema_objs,
            table_node_mapping,
            VectorStoreIndex,
        )

        from llama_index.core.indices.struct_store import SQLTableRetrieverQueryEngine

        custom_txt2sql_prompt = """Given an input question, construct a syntactically correct SQL query to run, then look at the results of the query and return a comprehensive and detailed answer. Ensure that you:
            - Select only the relevant columns needed to answer the question.
            - Use correct column and table names as provided in the schema description. Avoid querying for columns that do not exist.
            - Qualify column names with the table name when necessary, especially when performing joins.
            - Use aggregate functions appropriately and include performance optimizations such as WHERE clauses and indices.
            - Add additional related information for the user.
            - Use background & definitions provided for more detailed answer. Follow the instructions.
            - Your are provided with several tables each for a different proram area, ensure you retrive the relevant table.
            - do not hallucinate column names. If you can't  find a column name, do not write the sql query say I'm not sure.

             When answering questions that include the string "PreP," utilize the LinelistPrepAssessments table to construct the SQL code.
             When answering questions that include the string "OVC" utilize the  LineListOVCEligibilityAndEnrollments table to construct the SQL code.
             When answering questions that include the string "OTZ" utilize the  LineListOTZEligibilityAndEnrollments table to construct the SQL code.
             When answering questions that include the string " HEI or infants" utilize the  LinelistHEI table to construct the SQL code.
             When answering questions that include the string "PBFW," utilize the LineListPBFW table to construct the SQL code.
             When answering questions that include the string "HTS" or "HIV tests"  utilize the LineListTransHTS table to construct the SQL code.


             Special Instructions:
            - Treat "txcurr", "active patients on treatment" and "current on art" as interchangeable terms in your queries.
            - Exposed Infants (HEI) and HEI are used interchangably.
            - Default to using averages for aggregation if not specified by the user question.
            - If the requested date range is not available in the database, inform the user that data is not available for that time period.
            - Use bold and large fonts to highlight keywords in your answer.
            - If the date is not available, your answer will be: Data is not available for the requested date range. Please modify your query to include a valid date range.
            - Calculate date ranges dynamically based on the current date or specific dates mentioned in user queries. Use relative time expressions such as "last month" or "past year".
            - If a query fails to execute, suggest debugging tips or provide alternative queries. Ensure to handle common SQL errors gracefully."
            - If the query is ambiguous, generate a clarifying question to better understand the user's intent or request additional necessary parameters.
            - Use indexed columns for joins and WHERE clauses to speed up query execution. Use `EXPLAIN` plans for complex queries to ensure optimal performance.
            - Join ON "PatientPKHASH" AND "MFLCode" for queries that require joins.
            - txcurr is where IsTxcurr=1.
            - current on art is where IsTxcurr=1.
            - When NUPI = NULL means you have not been verified.
            - Verified clients are clients who have a Nupi Number.
            - Seroconversion is turning Positive from HIV test
            - Interruption in treatment (IIT) is the patients with Loss to Follow up outcome description."
            - Pre-exposure prophylaxis and PreP are used interchangably
            - Infected Infants also means HEI 

             Additional Instructions:

            When encountering the phrase 'as at' in a query prompt, interpret it as a requirement to filter records up to and including a specific date. Convert the 'as 
            at [Month Year]' phrase into a condition that ensures the query selects records up to the end of the specified month. For example, 'as at June 2024' should be 
            translated into a date filter for '<= 2024-06-30'. Incorporate this date condition into the SQL query accordingly.

            The key difference is that the "Differentiated Care" column refers to a model of multi-month dispensing, whereas "ONMMD" specifically denotes multi-month dispensing itself.

            Please confirm the variables names in the schema before generating a query

            You are required to use the following format, each taking one line:
            Question: Question here
            SQLQuery: SQL Query to run


            The text-to-SQL system that might be required to handle queries related to calculating proportions within a dataset. Your system should be able to generate SQL queries to calculate the proportion of a certain category within a dataset table.

            hints only gives you the columns, please use the hint to calculate proportions

            Example 1 :
            If a user asks, "What proportion of TxCurr,  have hypertension by county", your system should generate a SQL query like:

            SELECT County, COUNT(*) AS TotalTxCurr, SUM(CASE WHEN HasHypertension = 1 THEN 1 ELSE 0 END) AS TotalHypertension, SUM(CASE WHEN HasHypertension = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS ProportionHypertension FROM Linelist_FACTART WHERE ISTxCurr = 1 GROUP BY County;

            Example 2:
            If a user asks, "What is the proportion of clients screened for Prep per county", your system should generate a SQL query like:

            SELECT County, COUNT(*) AS ScreenedPrep, SUM(CASE WHEN ScreenedPrep = 1 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) AS ProportionScreenedForPrep FROM LinelistPrepAssessments GROUP BY County;


            Example 3 :
            If a user asks, "What is unsuppression rate of all active clients on treatment by county", your system should generate a SQL query like:

            SELECT County, COUNT(*) AS TotalPatientsWithValidVL, COUNT(CASE WHEN HighViremia = 1 THEN 1 END) AS UnsuppressedPatients, COUNT(CASE WHEN HighViremia = 1 THEN 1 END) * 100.0 / COUNT(*) AS UnsuppressionRate FROM Linelist_FACTART WHERE ISTxCurr = 1 AND HasValidVL = 1 GROUP BY County;

            The text-to-SQL system that might be required to handle queries related to calculating trends or rate of change. Your system should be able to generate SQL queries to calculate trend and increase rate.

            Instructions:

            Calculate the rates :Compute Rate Differences: Calculate change in rate(subtract the rate at end period-start period/start period): Multiply the rate difference by 100 to express it as a percentage.

            Example 1 :
            If a user asks, "What is the trend in positivity rates across different counties from January 2023 to June 2023, and which county experienced the greatest increase in positivity rate over this period?"", your system should generate a SQL query like:

            SELECT County, MAX(CASE WHEN Month = 1 THEN PositivityRate END) AS PositivityRate_Month1, MAX(CASE WHEN Month = 2 THEN PositivityRate END) AS PositivityRate_Month2, MAX(CASE WHEN Month = 3 THEN PositivityRate END) AS PositivityRate_Month3, MAX(CASE WHEN Month = 4 THEN PositivityRate END) AS PositivityRate_Month4, MAX(CASE WHEN Month = 5 THEN PositivityRate END) AS PositivityRate_Month5, MAX(CASE WHEN Month = 6 THEN PositivityRate END) AS PositivityRate_Month6, (MAX(CASE WHEN Month = 6 THEN PositivityRate END) - MAX(CASE WHEN Month = 1 THEN PositivityRate END)) AS PositivityRateDifference, CASE WHEN MAX(CASE WHEN Month = 1 THEN PositivityRate END) <> 0 THEN (((MAX(CASE WHEN Month = 6 THEN PositivityRate END) - MAX(CASE WHEN Month = 1 THEN PositivityRate END)) / MAX(CASE WHEN Month = 1 THEN PositivityRate END)) * 100) ELSE NULL END AS RateDifference FROM ( SELECT County, MONTH(TestDate) AS Month, COUNT(CASE WHEN FinalTestResult = 'Positive' THEN 1 END) AS PositiveTests, COUNT(*) AS TotalTests, CASE WHEN COUNT(*) <> 0 THEN COUNT(CASE WHEN FinalTestResult = 'Positive' THEN 1 END) * 100.0 / COUNT(*) ELSE NULL END AS PositivityRate FROM LineListTransHTS WHERE TestDate >= '2023-01-01' AND TestDate < '2023-07-01' GROUP BY County, MONTH(TestDate) ) AS PositivityRates GROUP BY County;
            when asked for a specific county, Partner or facility , order in descending and filter to the top county/partner/facility, otherwise provide a linelist

            The text-to-SQL system that might be required to handle queries related to joining different tablea. Your system should be able to generate SQL queries to joins different tables and selects the variables needed.
            Example 1 :
            If a user asks, "among Counties that conducted more than 10,000 HIV tests in 2023, which county has the highest number of active patients on treatment?, your system should generate a SQL query like:

            SQLQUERY: SELECT County, COUNT(*) AS TotalTxCurr FROM Linelist_FACTART WHERE County IN (SELECT County FROM LineListTransHTS WHERE YEAR(TestDate) = 2023 GROUP BY County HAVING COUNT(*) > 10000) AND ISTxCurr = 1 GROUP BY County ORDER BY TotalTxCurr DESC;

        """
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


class NaturalLanguageResponseRating(BaseModel):
    response_rating: int
    response_rating_comment: str | None = None


@router.post('/rate/{response_id}')
async def rate_response(rating: NaturalLanguageResponseRating, response_id: str):
    try:
        response_id_obj = ObjectId(response_id)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid response_id") from e

    TafsiriResp.update_one(
        {"_id": response_id_obj},
        {"$set": {"response_rating": rating.response_rating, "response_rating_comment": rating.response_rating_comment}}
    )

    return {"success": True}


# Endpoint to retrieve table descriptions
@router.get('/table_descriptions')
async def get_table_descriptions():
    try:
        tables_info = get_dictionary_info_cached()
        descriptions = [
            {"table_name": table.table_name, "description": table.context_str}
            for table in tables_info
        ]
        return {"tables": descriptions}
    except Exception as e:
        log.error(f"Error retrieving table descriptions: {e}")
        raise HTTPException(status_code=500, detail=str(e)) from e
