#!/bin/bash
# ==============================================================================
# Script tự động sao lưu CSDL MySQL & Dữ liệu SportZone trên môi trường Production
# Chạy hàng ngày qua Cron Job: xuất file .sql.gz và tự xóa file cũ sau 7 ngày
# ==============================================================================

PROJECT_DIR="/opt/sportzone"
BACKUP_DIR="/opt/sportzone/backups"
LOG_FILE="/opt/sportzone/logs/backup.log"
DATE=$(date +"%Y%m%d_%H%M%S")
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR"
mkdir -p "$PROJECT_DIR/logs"

echo "==================================================" >> "$LOG_FILE"
echo "[$DATE] Bắt đầu tiến trình sao lưu hệ thống SportZone..." >> "$LOG_FILE"

cd "$PROJECT_DIR" || exit 1

# 1. Đọc mật khẩu MySQL từ file .env
MYSQL_PASSWORD=$(grep -E '^MYSQL_PASSWORD=' .env | head -n 1 | cut -d '=' -f2- | tr -d '"' | tr -d "'")

if [ -z "$MYSQL_PASSWORD" ]; then
    echo "[$DATE] LỖI: Không tìm thấy MYSQL_PASSWORD trong file .env" >> "$LOG_FILE"
    exit 1
fi

# 2. Xuất và nén CSDL MySQL (mysqldump + gzip)
DB_BACKUP_FILE="$BACKUP_DIR/sportzone_db_$DATE.sql.gz"
docker compose -f docker-compose.prod.yml exec -T db mysqldump -u sportzone -p"$MYSQL_PASSWORD" --single-transaction --quick --default-character-set=utf8mb4 sportzone | gzip > "$DB_BACKUP_FILE"

if [ $? -eq 0 ] && [ -s "$DB_BACKUP_FILE" ]; then
    FILE_SIZE=$(du -h "$DB_BACKUP_FILE" | cut -f1)
    echo "[$DATE] Xuất CSDL thành công: $DB_BACKUP_FILE ($FILE_SIZE)" >> "$LOG_FILE"
else
    echo "[$DATE] LỖI: Sao lưu CSDL thất bại!" >> "$LOG_FILE"
    exit 1
fi

# 3. Tự động xóa các bản sao lưu cũ hơn RETENTION_DAYS ngày
DELETED_COUNT=$(find "$BACKUP_DIR" -type f -name "sportzone_db_*.sql.gz" -mtime +$RETENTION_DAYS -delete -print | wc -l)
echo "[$DATE] Đã dọn dẹp $DELETED_COUNT bản sao lưu cũ hơn $RETENTION_DAYS ngày." >> "$LOG_FILE"

echo "[$DATE] Hoàn thành sao lưu thành công!" >> "$LOG_FILE"
