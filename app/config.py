import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER")
LLM_MODEL = os.getenv("LLM_MODEL")

if not LLM_PROVIDER or not LLM_MODEL:
    raise ValueError("LLM_PROVIDER and LLM_MODEL must be set in the environment or .env file.")
