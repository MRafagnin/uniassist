param(
    [Parameter(Position = 0)]
    [ValidateSet("ingest", "scrape", "scrape-web", "scrape-sn", "clean", "index", "api", "ui", "eval", "test", "lint")]
    [string]$Task = "test"
)

$ErrorActionPreference = "Stop"

switch ($Task) {
    "scrape-web" { uv run python -m uniassist.ingest.scraper }
    "scrape-sn"  { uv run python -m uniassist.ingest.servicenow_scraper }
    "scrape" {
        uv run python -m uniassist.ingest.scraper
        uv run python -m uniassist.ingest.servicenow_scraper
    }
    "clean"  { uv run python -m uniassist.ingest.clean }
    "index"  { uv run python -m uniassist.ingest.build_index }
    "ingest" {
        uv run python -m uniassist.ingest.scraper
        uv run python -m uniassist.ingest.servicenow_scraper
        uv run python -m uniassist.ingest.clean
        uv run python -m uniassist.ingest.build_index
    }
    "api"    { uv run uvicorn uniassist.api:app --reload --host 127.0.0.1 --port 8000 }
    "ui"     { uv run streamlit run src/uniassist/ui/app.py }
    "eval"   { uv run python -m eval.run_eval }
    "test"   { uv run pytest }
    "lint"   { uv run ruff check . }
}
