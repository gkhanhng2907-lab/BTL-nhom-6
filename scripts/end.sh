#!/bin/bash

docker-compose down -v

# Xóa file database cũ nếu tồn tại trong src/
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_PATH="$SCRIPT_DIR/../src/phishing_system.db"

if [ -f "$DB_PATH" ]; then
    rm -f "$DB_PATH"
    echo -e "\033[0;32mDa xoa file database cu: $DB_PATH\033[0m"
fi