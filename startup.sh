#!/bin/bash

# Đợi các dịch vụ khác khởi động nếu cần
# sleep 15

# Di chuyển đến thư mục dự án Django
# cd /home/aais/Documents/ifshop || exit 1

# Lấy cấu hình từ app.yml
PORT_APP=$(grep 'PORT_APP' app.yml | awk '{print $2}' | tr -d '[:space:]')
NUM_WORKERS=$(grep 'NUM_WORKERS' app.yml | awk '{print $2}' | tr -d '[:space:]')
LOG_LEVEL=$(grep 'LOG_LEVEL' app.yml | awk '{print $2}' | tr -d '[:space:]')

# Mặc định LOG_LEVEL = warning nếu không cấu hình
LOG_LEVEL=${LOG_LEVEL:-warning}

echo "PORT_APP is: $PORT_APP"
echo "NUM_WORKERS is: $NUM_WORKERS"
echo "LOG_LEVEL is: $LOG_LEVEL"

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

# Chạy server Django
# Sử dụng Gunicorn cho production với số worker chỉ định trong app.yml
# Nếu bạn chưa cài gunicorn, hãy chạy pip install gunicorn trước nhé
gunicorn api_crud.wsgi:application --bind 0.0.0.0:$PORT_APP --workers $NUM_WORKERS --log-level $LOG_LEVEL
