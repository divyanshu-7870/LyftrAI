from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any, Union

class ChatRequest(BaseModel):
    session_id: str
    message: str
    system_prompt: Optional[str] = None

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("session_id must not be empty")
        v = v.strip()
        if len(v) > 128:
            raise ValueError("session_id must be between 1 and 128 characters")
        return v

    @field_validator("message")
    @classmethod
    def validate_message(cls, v: str) -> str:
        if v is None:
            raise ValueError("message is required")
        trimmed = v.strip()
        if not trimmed:
            raise ValueError("message must not be empty or whitespace only")
        if len(trimmed) > 4000:
            raise ValueError("message must not exceed 4000 characters after trimming")
        return trimmed

class ChatMetadata(BaseModel):
    resolution_source: str
    model: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    key_id: Optional[str] = None
    fallback_attempts: int

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    metadata: ChatMetadata

class HealthResponse(BaseModel):
    status: str
    keys_configured: int
    cache_enabled: bool

class MessageItem(BaseModel):
    role: str
    content: str
    metadata: Optional[Dict[str, Any]] = None

class SessionMessagesResponse(BaseModel):
    session_id: str
    messages: List[MessageItem]
