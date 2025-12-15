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
    openai_search_model: str = Field(default="gpt-4o-mini-search-preview")
    openai_score_model: str = Field(default="gpt-5-mini")
    gemini_search_model: str = Field(default="models/gemini-2.5-flash")
    gemini_score_model: str = Field(default="models/gemini-2.5-flash")
    agent_search_provider: str = Field(
        default="auto",
        description="PoCの検索/groundingに使うプロバイダ（auto|gemini|openai）",
    )
    agent_score_provider: str = Field(
        default="auto",
        description="PoCのスコアリングに使うプロバイダ（auto|gemini|openai）",
    )
    agent_debug: bool = Field(default=False, description="エージェントPoCのデバッグログを有効化")
    agent_save_runs: bool = Field(default=False, description="エージェントPoCの入出力をruns/へ保存")
    party_limit: int = Field(default=6, description="PoCで処理する政党数上限（タイムアウト回避）")
    max_evidence_per_party: int = Field(default=2, description="PoCで各党から収集する根拠URL上限")

    model_config = SettingsConfigDict(
        env_file=["../.env", ".env"],
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
