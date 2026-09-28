# Инструмент визуализации с драйверами хранилища и движка запросов, вшитыми в
# образ: на паре сети может не быть. Работает от пользователя образа (uid 1000).
# Версии всех пакетов, включая транзитивные, — из constraints.txt рядом.
FROM apache/superset:6.1.0
USER root
# Superset 6 живёт в /app/.venv (uv); системный pip ставит в другой интерпретатор.
COPY constraints.txt /tmp/constraints.txt
RUN uv pip install --python /app/.venv/bin/python --no-cache --constraint /tmp/constraints.txt \
    "clickhouse-connect==1.9.0" "trino==0.340.0"
COPY superset_config.py /app/pythonpath/superset_config.py
USER superset
