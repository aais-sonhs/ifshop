#!/bin/bash

set -u

timestamp() {
    date '+%Y-%m-%d %H:%M:%S %z'
}

log_info() {
    printf '[%s] [INFO] %s\n' "$(timestamp)" "$1"
}

log_error() {
    printf '[%s] [ERROR] %s\n' "$(timestamp)" "$1" >&2
}

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -f "$SCRIPT_DIR/app.yml" ]; then
    CONFIG_FILE="$SCRIPT_DIR/app.yml"
elif [ -f "$SCRIPT_DIR/app.yaml" ]; then
    CONFIG_FILE="$SCRIPT_DIR/app.yaml"
else
    log_error "Không tìm thấy app.yml hoặc app.yaml trong $SCRIPT_DIR"
    exit 1
fi

PORT_APP="$(
    sed -n 's/^[[:space:]]*PORT_APP[[:space:]]*:[[:space:]]*//p' "$CONFIG_FILE" \
        | head -n 1 \
        | tr -d "'\"[:space:]"
)"

case "$PORT_APP" in
    ''|*[!0-9]*)
        log_error "PORT_APP trong $CONFIG_FILE không hợp lệ."
        exit 1
        ;;
esac

if ! command -v curl >/dev/null 2>&1; then
    log_error "Máy chưa cài curl."
    exit 1
fi

SCHEDULER_URL="http://127.0.0.1:${PORT_APP}/api/internal/run-scheduled-emails/"
log_info "Bắt đầu kiểm tra các email đến hạn."

RESPONSE="$(curl \
    --silent \
    --show-error \
    --max-time 55 \
    --request POST \
    --header "X-Forwarded-Proto: https" \
    --write-out $'\n%{http_code}' \
    "$SCHEDULER_URL")"
CURL_EXIT=$?

if [ "$CURL_EXIT" -ne 0 ]; then
    log_error "Không gọi được email scheduler (curl exit $CURL_EXIT)."
    exit "$CURL_EXIT"
fi

HTTP_STATUS="${RESPONSE##*$'\n'}"
RESPONSE_BODY="${RESPONSE%$'\n'*}"

case "$HTTP_STATUS" in
    2??)
        log_info "Email scheduler hoàn tất với HTTP $HTTP_STATUS. Kết quả: $RESPONSE_BODY"
        ;;
    *)
        log_error "Email scheduler thất bại với HTTP $HTTP_STATUS. Phản hồi: $RESPONSE_BODY"
        exit 1
        ;;
esac
