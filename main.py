from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routes import tafsiri_api

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


@app.get("/api/healthchecker")
def root():
    return {"message": "Welcome to data map, we are up and running"}


# Run the FastAPI application
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
