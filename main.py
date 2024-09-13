from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import tafsiri_api, config_api, tafsiriV2_api

app = FastAPI()

origins = [
    "*",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tafsiri_api.router, tags=[
                   'Text2SQL'], prefix='/api/text2sql')
app.include_router(config_api.router, tags=['Config'], prefix='/api/config')
app.include_router(tafsiriV2_api.router, tags=[
                   'TafsiriV2'], prefix='/api/tafsiri')


@app.get("/api/healthchecker")
def root():
    return {"message": "Welcome to Tafsiri, we are up and running"}


# Run the FastAPI application
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
