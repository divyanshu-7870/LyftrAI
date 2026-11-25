#!/bin/bash

# Lyftr AI Demo Helper Script
# Target Deployed Backend: https://lyftrai-p0mb.onrender.com

BACKEND_URL="${BACKEND_URL:-https://lyftrai-p0mb.onrender.com}"

# Pretty printing helper using python3 built-in json.tool (always available)
pretty_json() {
    python3 -m json.tool 2>/dev/null || cat
}

case "$1" in
    health)
        echo "============================================="
        echo "=== HEALTH CHECK: GET /health ==="
        echo "============================================="
        curl -s -w "\nHTTP Status: %{http_code}\n" "${BACKEND_URL}/health" | while read -r line; do
            if [[ "$line" =~ ^HTTP ]]; then
                echo "$line"
            elif [ -n "$line" ]; then
                echo "$line" | pretty_json
            fi
        done
        ;;

    failover)
        echo "=========================================================="
        echo "=== FAILOVER: X-Simulate-Failure: key_1=429 -> key_2 ==="
        echo "=========================================================="
        curl -s -X POST "${BACKEND_URL}/chat" \
            -H "Content-Type: application/json" \
            -H "X-Simulate-Failure: key_1=429" \
            -d '{"session_id": "video-failover-1", "message": "What is the capital of Japan? One word."}' \
            | pretty_json
        echo ""
        ;;

    allfail)
        echo "=========================================================="
        echo "=== ALL FAIL: X-Simulate-Failure: *=429 (Expect 503) ==="
        echo "=========================================================="
        curl -s -i -X POST "${BACKEND_URL}/chat" \
            -H "Content-Type: application/json" \
            -H "X-Simulate-Failure: *=429" \
            -d '{"session_id": "video-all-fail-1", "message": "This request must fail."}'
        echo ""
        ;;

    failed-history)
        echo "=========================================================="
        echo "=== FAILED HISTORY: Expect 404 session not found ==="
        echo "=========================================================="
        curl -s -i "${BACKEND_URL}/sessions/video-all-fail-1/messages"
        echo ""
        ;;

    history-create)
        echo "=========================================================="
        echo "=== HISTORY CREATE: Create session video-history-1 ==="
        echo "=========================================================="
        curl -s -X POST "${BACKEND_URL}/chat" \
            -H "Content-Type: application/json" \
            -d '{"session_id": "video-history-1", "message": "Remember the number 7392."}' \
            | pretty_json
        echo ""
        ;;

    history)
        echo "=========================================================="
        echo "=== HISTORY: GET /sessions/video-history-1/messages ==="
        echo "=========================================================="
        curl -s "${BACKEND_URL}/sessions/video-history-1/messages" | pretty_json
        echo ""
        ;;

    *)
        echo "Usage: ./demo.sh [health|failover|allfail|failed-history|history-create|history]"
        exit 1
        ;;
esac
