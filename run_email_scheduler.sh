#!/bin/bash

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/app.yml" ]; then
    CONFIG_FILE="$SCRIPT_DIR/app.yml"
elif [ -f "$SCRIPT_DIR/app.yaml" ]; then
    CONFIG_FILE="$SCRIPT_DIR/app.yaml"
else
    echo "Không tìm thấy app.yml hoặc app.yaml trong $SCRIPT_DIR" >&2
    exit 1
fi

PORT_APP="$(
    sed -n 's/^[[:space:]]*PORT_APP[[:space:]]*:[[:space:]]*//p' "$CONFIG_FILE" \
        | head -n 1 \
        | tr -d "'\"[:space:]"
)"

case "$PORT_APP" in
    ''|*[!0-9]*)
        echo "PORT_APP trong $CONFIG_FILE không hợp lệ." >&2
        exit 1
        ;;
esac

if ! command -v curl >/dev/null 2>&1; then
    echo "Máy chưa cài curl." >&2
    exit 1
fi

curl \
    --silent \
    --show-error \
    --fail \
    --max-time 55 \
    --output /dev/null \
    --request POST \
    --header "X-Forwarded-Proto: https" \
    "http://127.0.0.1:${PORT_APP}/api/internal/run-scheduled-emails/"
