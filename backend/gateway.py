import time
import logging
from typing import List, Dict, Any, Optional, Tuple
import litellm
from litellm import completion, Cache
from litellm.exceptions import (
    RateLimitError,
    APIError,
    Timeout,
    ServiceUnavailableError,
    InternalServerError,
    BadGatewayError,
    AuthenticationError
)
from backend.config import settings

logger = logging.getLogger("gateway")

# Configure LiteLLM built-in cache
# Using local in-memory cache as permitted by assignment
litellm.cache = Cache(type="local")

class ProviderUnavailableException(Exception):
    """Raised when all configured keys in the pool have failed."""
    pass

class SimulatedFailureException(Exception):
    """Raised when a key is forced to fail via X-Simulate-Failure."""
    def __init__(self, key_id: str, status_code: int):
        self.key_id = key_id
        self.status_code = status_code
        super().__init__(f"Simulated failure for {key_id} with status {status_code}")

def parse_simulated_failures(header_value: Optional[str]) -> Dict[str, int]:
    """
    Parses X-Simulate-Failure header.
    Format: comma-separated <key_id>=<status> pairs; * means every key.
    Statuses: 429, 500, 502, 503.
    e.g. 'key_1=429', 'key_1=429,key_2=500', '*=429'
    """
    if not header_value or not settings.ENABLE_FAILURE_SIMULATION:
        return {}
    
    simulations: Dict[str, int] = {}
    tokens = [t.strip() for t in header_value.split(",") if t.strip()]
    for token in tokens:
        if "=" in token:
            k, v = token.split("=", 1)
            k = k.strip()
            try:
                status = int(v.strip())
                if status in (429, 500, 502, 503):
                    simulations[k] = status
            except ValueError:
                continue
    return simulations

def execute_chat_completion(
    messages: List[Dict[str, str]],
    simulate_header: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Executes completion across the key pool with automatic fallback and caching.
    Returns: (reply_text, metadata_dict)
    metadata_dict contains:
      - resolution_source: 'LIVE_INFERENCE' or 'LLM_CACHE'
      - model: string
      - latency_ms: int
      - input_tokens: int
      - output_tokens: int
      - key_id: Optional[str] (null on LLM_CACHE)
      - fallback_attempts: int (0 on LLM_CACHE)
    """
    simulations = parse_simulated_failures(simulate_header)
    keys = settings.key_pool
    if not keys:
        raise ProviderUnavailableException("No API keys configured.")

    fallback_attempts = 0
    t0 = time.time()

    for idx, key in enumerate(keys):
        key_id = f"key_{idx + 1}"

        # Check simulated failure
        # Matches specific key_id or wildcard '*'
        sim_status = simulations.get(key_id) or simulations.get("*")
        if sim_status is not None:
            logger.info("Simulating failure for %s with HTTP %d", key_id, sim_status)
            fallback_attempts += 1
            continue

        try:
            response = completion(
                model=settings.LLM_MODEL,
                messages=messages,
                api_key=key,
                caching=True
            )
            t1 = time.time()
            latency_ms = int(round((t1 - t0) * 1000))

            reply = response.choices[0].message.content or ""
            hidden = getattr(response, "_hidden_params", {}) or {}
            is_cache_hit = bool(hidden.get("cache_hit", False))

            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "completion_tokens", 0) or 0)

            if is_cache_hit:
                resolution_source = "LLM_CACHE"
                assigned_key_id = None
                assigned_fallback_attempts = 0
            else:
                resolution_source = "LIVE_INFERENCE"
                assigned_key_id = key_id
                assigned_fallback_attempts = fallback_attempts

            metadata = {
                "resolution_source": resolution_source,
                "model": settings.LLM_MODEL,
                "latency_ms": latency_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "key_id": assigned_key_id,
                "fallback_attempts": assigned_fallback_attempts
            }
            return reply, metadata

        except (RateLimitError, APIError, Timeout, ServiceUnavailableError, InternalServerError, BadGatewayError) as e:
            logger.warning("Key %s failed with exception: %s. Falling back to next key.", key_id, str(e))
            fallback_attempts += 1
            continue
        except Exception as e:
            # Check if exception status indicates provider failure (429, 5xx)
            err_str = str(e)
            status_code = getattr(e, "status_code", None)
            if status_code in (429, 500, 502, 503, 504) or "429" in err_str or "500" in err_str or "quota" in err_str.lower():
                logger.warning("Key %s hit error %s. Falling back to next key.", key_id, err_str)
                fallback_attempts += 1
                continue
            else:
                # Any other provider error also fails over
                logger.warning("Key %s unexpected provider error: %s. Failing over.", key_id, err_str)
                fallback_attempts += 1
                continue

    # If all keys failed
    raise ProviderUnavailableException("all providers unavailable")
