# Оболочка службы сборщика данных. Программу пишет студент: она монтируется в
# /app/src и запускается точкой входа. Реализации сборщика в стенде нет.
FROM python:3.13.15-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

# Зависимости студента: если рядом с его программой лежит requirements.txt,
# он ставится при сборке образа (`docker compose build collector`).
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh && \
    useradd --create-home --uid 1000 collector && \
    mkdir -p /data/raw && chown -R collector /data
USER collector

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["record"]
