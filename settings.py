from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URL: str
    DATABASE_NAME: str

    REPORTING_DB: str
    REPORTING_USER: str
    REPORTING_PASSWORD: str
    REPORTING_HOST: str
    OPENAI_KEY: str

    OM_HOST: str
    OM_JWT: str

    class Config:
        env_file = './.env'
        extra = 'ignore'


settings = Settings()
