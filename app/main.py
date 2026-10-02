import os
from dotenv import load_dotenv
load_dotenv()

import traceback
import re
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Startup check for API key
provider = os.getenv("LLM_PROVIDER", "google_genai")
if provider in ("google", "google_genai") and not (os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")):
    raise RuntimeError(f"Missing API key for provider {provider}. Please set GOOGLE_API_KEY in .env")

from app.graph import graph

app = FastAPI()

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., max_length=500)

class ChatResponse(BaseModel):
    reply: str
    sop_ids: list[str]
    trace: list[str]
    reply_path: str

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/", response_class=HTMLResponse)
def root():
    if not os.path.exists("static/index.html"):
        return "UI not found"
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()

@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    try:
        config = {"configurable": {"thread_id": req.session_id}}
        events = list(graph.stream({"user_message": req.message}, config=config))
        
        trace = [list(e.keys())[0] for e in events]
        state = graph.get_state(config).values
        
        reply_text = state.get("reply", "No reply generated.")
        
        if "service_unavailable_reply" in trace:
            reply_path = "service unavailable"
        elif "template_reply" in trace or "all_clear_reply" in trace or "honest_fallback" in trace or "no_coverage_reply" in trace:
            reply_path = "deterministic (no LLM)"
        else:
            retries = state.get("retries", 0)
            llm_used = state.get("llm_used", {})
            reply_path = f"llm attempt {retries + 1} ({llm_used.get('compose_reply', 'N/A')})"
            
        cited_ids = list(set(re.findall(r'\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)*-\d+\b', reply_text)))
        
        return {
            "reply": reply_text,
            "sop_ids": cited_ids,
            "trace": trace,
            "reply_path": reply_path
        }
    except Exception:
        traceback.print_exc()
        return {
            "reply": "Sorry, an unexpected error occurred while processing your request.",
            "sop_ids": [],
            "trace": [],
            "reply_path": "error"
        }
