from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    api_key: str = "dev-key-change-me"
    # Paid API keys — kept optional for backward compat, default empty
    deepgram_api_key: str = ""
    anthropic_api_key: str = ""
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = "21m00Tcm4TlvDq8ikWAM"
    discord_bot_token: str = ""
    discord_guild_id: str = ""
    database_url: str = "sqlite:///./calls.db"
    salesforce_username: str = ""
    salesforce_password: str = ""
    salesforce_security_token: str = ""
    salesforce_domain: str = "login"
    gsa_db_path: str = ""  # path to GatewayGSA's SQLite DB file
    host: str = "0.0.0.0"
    port: int = 8000

    # Free local stack
    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    whisper_model_size: str = "base"  # tiny/base/small/medium — base is a good balance
    edge_tts_voice: str = "en-US-AriaNeural"

    class Config:
        env_file = ".env"


settings = Settings()