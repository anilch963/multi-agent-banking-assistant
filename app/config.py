"""Central configuration. Everything is overridable through environment variables."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("BANK_DATA_DIR", BASE_DIR / "data"))
DB_PATH = Path(os.getenv("BANK_DB_PATH", DATA_DIR / "bank.db"))
CHROMA_DIR = Path(os.getenv("BANK_CHROMA_DIR", DATA_DIR / "chroma"))
KB_DIR = BASE_DIR / "knowledge_base"

BANK_NAME = "Anil Bank"  # fictional bank used for the demo data

OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
OPENAI_TEMPERATURE = os.getenv("OPENAI_TEMPERATURE")  # None -> model default

KB_COLLECTION = "bank_knowledge"
MAX_AGENTS_PER_TURN = 3   # how many specialists the supervisor may fan out to
MAX_TOOL_STEPS = 6        # tool-calling iterations per specialist
HISTORY_WINDOW = 12       # conversation messages passed to each agent
