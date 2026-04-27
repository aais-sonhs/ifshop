#!/bin/bash

# Đợi các dịch vụ khác khởi động nếu cần
sleep 15

# Di chuyển đến thư mục dự án Django
cd /home/aais/Documents/ifshop || exit 1

if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi

# Lấy cấu hình từ app.yml
PORT_APP=$(grep 'PORT_APP' app.yml | awk '{print $2}' | tr -d '[:space:]')
NUM_WORKERS=$(grep 'NUM_WORKERS' app.yml | awk '{print $2}' | tr -d '[:space:]')
LOG_LEVEL=$(grep 'LOG_LEVEL' app.yml | awk '{print $2}' | tr -d '[:space:]')

# Mặc định LOG_LEVEL = warning nếu không cấu hình
LOG_LEVEL=${LOG_LEVEL:-warning}
DJANGO_ENV=${DJANGO_ENV:-production}
DJANGO_SECRET_KEY_FILE=${DJANGO_SECRET_KEY_FILE:-"$HOME/.config/ifshop/secret_key"}

echo "PORT_APP is: $PORT_APP"
echo "NUM_WORKERS is: $NUM_WORKERS"
echo "LOG_LEVEL is: $LOG_LEVEL"
echo "DJANGO_ENV is: $DJANGO_ENV"

if [ -z "$DJANGO_SECRET_KEY" ]; then
  mkdir -p "$(dirname "$DJANGO_SECRET_KEY_FILE")"
  if [ ! -s "$DJANGO_SECRET_KEY_FILE" ]; then
    python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())" > "$DJANGO_SECRET_KEY_FILE"
    chmod 600 "$DJANGO_SECRET_KEY_FILE"
  fi
  DJANGO_SECRET_KEY=$(cat "$DJANGO_SECRET_KEY_FILE")
fi

export DJANGO_ENV
export DJANGO_SECRET_KEY
export DJANGO_SECRET_KEY_FILE

# Kill process đang chiếm port nếu có
PID=$(lsof -t -i :$PORT_APP)
if [ -n "$PID" ]; then
  echo "Found process on port $PORT_APP (PID: $PID), killing..."
  kill $PID
  sleep 1
  if kill -0 $PID 2>/dev/null; then
    echo "Process $PID vẫn chưa dừng, dùng SIGKILL..."
    kill -9 $PID
  else
    echo "Process $PID đã dừng."
  fi
else
  echo "Không có process nào đang chiếm port $PORT_APP."
fi

# Xác định access log flag
# Nếu log level >= warning thì tắt access log hoàn toàn để tiết kiệm CPU
ACCESS_LOG_FLAG="--no-access-log"
if [ "$LOG_LEVEL" = "info" ] || [ "$LOG_LEVEL" = "debug" ]; then
  ACCESS_LOG_FLAG="--access-log"
fi

# Thu gom static files (CSS, JS, images) vào static_root/
python manage.py collectstatic --noinput

# Chạy Uvicorn (ASGI)
python -m uvicorn config.asgi:application --host 0.0.0.0 --port $PORT_APP --workers $NUM_WORKERS --log-level $LOG_LEVEL $ACCESS_LOG_FLAG
