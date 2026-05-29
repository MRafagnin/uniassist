"""Env-driven configuration via pydantic-settings."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Ollama
    ollama_host: str = "http://localhost:11434"
    model_chat: str = "qwen2.5:7b-instruct"
    model_embed: str = "nomic-embed-text"
    model_judge: str = "llama3.1:8b"

    # Paths
    corpus_dir: Path = REPO_ROOT / "data"
    chroma_dir: Path = REPO_ROOT / "data" / "chroma"
    sqlite_path: Path = REPO_ROOT / "data" / "uniassist.db"

    # Retrieval / chunking
    retrieval_k: int = 5
    retrieval_fetch_k: int = 20
    chunk_size: int = 800
    chunk_overlap: int = 120

    # Scraper
    scrape_seed_url: str = "https://www.sydney.edu.au/students/student-it.html"
    scrape_max_pages: int = 150
    scrape_max_depth: int = 3
    scrape_delay_seconds: float = 1.0
    scrape_user_agent: str = Field(
        default="UniAssistBot/0.1 (+https://github.com/MRafagnin/uniassist)"
    )
    # Only follow URLs whose path starts with one of these prefixes (same-host).
    # Keeps the crawl focused on student-IT content instead of the whole sydney.edu.au site.
    scrape_path_prefixes: tuple[str, ...] = (
        "/students/student-it",
        "/students/log-in-to-university-systems",
        "/students/canvas",
        "/students/minimum-computing-requirements",
        "/students/keeping-your-information-safe",
        "/students/scams",
        "/students/new-students/digital-set-up",
    )

    @property
    def raw_dir(self) -> Path:
        return self.corpus_dir / "raw"

    @property
    def raw_servicenow_dir(self) -> Path:
        return self.corpus_dir / "raw_servicenow"

    @property
    def raw_manual_dir(self) -> Path:
        return self.corpus_dir / "raw_manual"

    @property
    def processed_dir(self) -> Path:
        return self.corpus_dir / "processed"


settings = Settings()
