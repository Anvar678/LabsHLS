#!/bin/sh
# Режим передаётся первым аргументом: record | backfill | produce | replay.
# Точка входа программы студента — /app/src/main.py, режим приходит в
# COLLECTOR_MODE и первым аргументом. Каталог вывода задаёт оболочка:
# запись потока и загрузка истории лежат в разных префиксах слоя сырых данных.
set -eu
mode="${1:-record}"
if [ ! -f /app/src/main.py ]; then
  echo "collector: /app/src/main.py не найден — положите программу в collector/src" >&2
  exit 78
fi
raw="${COLLECTOR_RAW_DIR:-/data/raw}"
case "$mode" in
  backfill) out="$raw/history" ;;
  *)        out="$raw/stream" ;;
esac
mkdir -p "$out"
export COLLECTOR_MODE="$mode" COLLECTOR_OUT_DIR="$out"
exec python /app/src/main.py "$@"
