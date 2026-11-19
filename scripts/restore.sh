#!/bin/bash
# ==============================================================================
# Script khôi phục CSDL MySQL SportZone từ bản sao lưu .sql.gz
# Cách dùng:
#   ./scripts/restore.sh                                  (Tự động khôi phục bản mới nhất)
#   ./scripts/restore.sh /opt/sportzone/backups/file.sql.gz (Khôi phục file chỉ định)
# ==============================================================================

PROJECT_DIR="/opt/sportzone"
BACKUP_DIR="/opt/sportzone/backups"

cd "$PROJECT_DIR" || exit 1

BACKUP_FILE="$1"
if [ -z "$BACKUP_FILE" ]; then
    # Lấy file mới nhất trong thư mục backups
    BACKUP_FILE=$(ls -t "$BACKUP_DIR"/sportzone_db_*.sql.gz 2>/dev/null | head -n 1)
fi

if [ -z "$BACKUP_FILE" ] || [ ! -f "$BACKUP_FILE" ]; then
    echo "LỖI: Không tìm thấy file sao lưu hợp lệ nào!"
    exit 1
fi

MYSQL_PASSWORD=$(grep -E '^MYSQL_PASSWORD=' .env | head -n 1 | cut -d '=' -f2- | tr -d '"' | tr -d "'")

if [ -z "$MYSQL_PASSWORD" ]; then
    echo "LỖI: Không tìm thấy MYSQL_PASSWORD trong .env"
    exit 1
fi

echo "=================================================="
echo "BẮT ĐẦU KHÔI PHỤC CSDL TỪ: $BACKUP_FILE"
echo "=================================================="

gunzip < "$BACKUP_FILE" | docker compose -f docker-compose.prod.yml exec -T db mysql -u sportzone -p"$MYSQL_PASSWORD" sportzone

if [ $? -eq 0 ]; then
    echo "THÀNH CÔNG: Đã khôi phục CSDL SportZone hoàn tất!"
else
    echo "THẤT BẠI: Khôi phục CSDL gặp lỗi!"
    exit 1
fi
