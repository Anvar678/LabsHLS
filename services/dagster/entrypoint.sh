#!/bin/sh
# Конфигурация экземпляра — файл стенда, а не студента: при каждом запуске
# переписывается из образа, чтобы правка образа доезжала до домашнего каталога.
set -eu
mkdir -p "$DAGSTER_HOME"
cp /opt/dagster/dagster.yaml "$DAGSTER_HOME/dagster.yaml"
exec "$@"
