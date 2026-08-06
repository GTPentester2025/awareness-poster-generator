import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    openai_api_key: str
    openai_text_model: str
    canva_client_id: str
    canva_client_secret: str
    base_url: str
    out_dir: Path
    token_path: Path


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    if env is None:
        load_dotenv()
        env = os.environ
    return Settings(
        openai_api_key=env["OPENAI_API_KEY"],
        openai_text_model=env.get("OPENAI_TEXT_MODEL", "gpt-4o-mini"),
        canva_client_id=env["CANVA_CLIENT_ID"],
        canva_client_secret=env["CANVA_CLIENT_SECRET"],
        base_url=env.get("BASE_URL", "http://127.0.0.1:8000"),
        out_dir=Path(env.get("OUT_DIR", "out")),
        token_path=Path(env.get("TOKEN_PATH", "token.json")),
    )
