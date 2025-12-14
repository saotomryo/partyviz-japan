from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数から設定を読み込む。"""

    database_url: str = Field(
        default="postgresql+psycopg://partyviz:partyviz@localhost:5432/partyviz",
        description="SQLAlchemy接続文字列（psycopg v3 ドライバ形式）",
    )
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    vite_api_base: str | None = None
    admin_api_key: str | None = None
    use_dummy_agents: bool = Field(default=False, description="エージェントをダミー実装で動かす場合にtrue")

    model_config = SettingsConfigDict(
        env_file=["../.env", ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
