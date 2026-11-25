from contextlib import asynccontextmanager
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder

from backend.config import settings
from backend.database import (
    init_db,
    check_db_health,
    get_messages_by_session,
    add_message,
    session_exists
)
from backend.models import (
    ChatRequest,
    ChatResponse,
    ChatMetadata,
    HealthResponse,
    SessionMessagesResponse,
    MessageItem
)
from backend.gateway import execute_chat_completion, ProviderUnavailableException

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database schema on startup
    await init_db()
    yield

app = FastAPI(title="Lyftr AI LLM Gateway", lifespan=lifespan)

# Setup CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if settings.cors_origins else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler for RequestValidationError (422) using jsonable_encoder
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(exc.errors())}
    )

# Exception handler for HTTPException to ensure JSON with "detail"
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )

# Generic exception handler to prevent unhandled 500 tracebacks or HTML pages
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error"}
    )

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Returns 200 once the app is running, the database is reachable and the key pool is loaded.
    { "status": "ok", "keys_configured": 2, "cache_enabled": true }
    """
    db_ok = await check_db_health()
    if not db_ok:
        raise HTTPException(status_code=503, detail="database unavailable")
    
    keys_count = len(settings.key_pool)
    return HealthResponse(
        status="ok",
        keys_configured=keys_count,
        cache_enabled=True
    )

@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(
    req: ChatRequest,
    x_simulate_failure: Optional[str] = Header(None, alias="X-Simulate-Failure")
):
    """
    POST /chat endpoint.
    Retrieves previous conversation history from SQLite, appends system prompt,
    executes LiteLLM completion with key failover, caches response, and saves new turns to SQLite.
    Failed requests (422 or 503) are never persisted to session history.
    """
    session_id = req.session_id
    user_msg = req.message
    system_prompt = req.system_prompt or settings.DEFAULT_SYSTEM_PROMPT

    # 1. Fetch previous session history from SQLite
    history_messages = await get_messages_by_session(session_id)

    # 2. Reconstruct complete message list sent to LLM
    # Cache key depends on model + full message list (system prompt + history + new message)
    llm_messages: List[Dict[str, str]] = []
    if system_prompt:
        llm_messages.append({"role": "system", "content": system_prompt})
    
    for hist in history_messages:
        llm_messages.append({
            "role": hist["role"],
            "content": hist["content"]
        })
    
    # Append the new user message
    llm_messages.append({"role": "user", "content": user_msg})

    # 3. Call LiteLLM gateway with failover & caching
    try:
        reply_text, meta_dict = execute_chat_completion(
            messages=llm_messages,
            simulate_header=x_simulate_failure
        )
    except ProviderUnavailableException:
        # Every key failed -> HTTP 503 {"detail": "all providers unavailable"}
        # Nothing added to history
        raise HTTPException(
            status_code=503,
            detail="all providers unavailable"
        )
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail="all providers unavailable"
        )

    # 4. On SUCCESS only, persist both user message and assistant reply to SQLite
    # Store assistant metadata with resolution_source, input_tokens, output_tokens
    await add_message(session_id, "user", user_msg)
    await add_message(
        session_id,
        "assistant",
        reply_text,
        metadata={
            "resolution_source": meta_dict["resolution_source"],
            "input_tokens": meta_dict["input_tokens"],
            "output_tokens": meta_dict["output_tokens"]
        }
    )

    # 5. Return exact ChatResponse
    return ChatResponse(
        session_id=session_id,
        reply=reply_text,
        metadata=ChatMetadata(**meta_dict)
    )

@app.get("/sessions/{session_id}/messages", response_model=SessionMessagesResponse)
async def get_session_messages(session_id: str):
    """
    Returns the stored history of one session from SQLite, oldest first, without the system prompt.
    Unknown session returns 404 {"detail": "session not found"}.
    """
    exists = await session_exists(session_id)
    if not exists:
        raise HTTPException(status_code=404, detail="session not found")

    messages_data = await get_messages_by_session(session_id)
    msg_items = []
    for m in messages_data:
        msg_items.append(MessageItem(
            role=m["role"],
            content=m["content"],
            metadata=m.get("metadata")
        ))

    return SessionMessagesResponse(
        session_id=session_id,
        messages=msg_items
    )
