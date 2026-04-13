# sleep 10

# cd ~/Documents/revenue_expenditure_manager

# Đợi các dịch vụ khác khởi động nếu cần
echo "Đang chờ PostgreSQL..."
while ! pg_isready -h 127.0.0.1 -p 6432 -U postgres >/dev/null 2>&1; do
    echo "Chưa kết nối được PostgreSQL, đợi 10 giây..."
    sleep 10
done
echo "PostgreSQL đã sẵn sàng!"

PORT_APP=8020

# Kill process đang chiếm port nếu có
PIDS=$(lsof -t -i :$PORT_APP)
if [ -n "$PIDS" ]; then
  echo "Found process(es) on port $PORT_APP: $PIDS"
  for pid in $PIDS; do
    echo "Killing PID $pid..."
    kill $pid
    sleep 1
    if kill -0 $pid 2>/dev/null; then
      echo "Process $pid vẫn chưa dừng, dùng SIGKILL..."
      kill -9 $pid
    else
      echo "Process $pid đã dừng."
    fi
  done
else
  echo "Không có process nào đang chiếm port $PORT_APP."
fi

python manage.py runserver 0.0.0.0:$PORT_APP
