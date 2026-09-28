#!/bin/bash
# Конфигурация Spark собирается при каждом запуске из двух частей:
#   1. файл подключения студента conf/spark/spark-defaults.conf (каталог
#      смонтирован в /opt/stand/conf/spark): каталог таблиц и хранилище.
#      Учётные данные в нём — ссылки ${ENV:ИМЯ} на переменные .env,
#      подставляются здесь; неизвестная переменная останавливает запуск;
#   2. строки стенда: расширения Iceberg и ресурсы. Они идут последними и при
#      совпадении ключа побеждают.
# Без файла подключения Spark работает, но каталога lake не видит.
set -eu
python3 - <<'PY'
import os
import re
import sys

src = "/opt/stand/conf/spark/spark-defaults.conf"
dst = "/opt/spark/conf/spark-defaults.conf"
stand = [
    "spark.sql.extensions  org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    "spark.driver.memory  2g",
    "spark.sql.shuffle.partitions  8",
]
ref = re.compile(r"\$\{ENV:([A-Za-z_][A-Za-z0-9_]*)\}")

lines = []
if os.path.isfile(src):
    with open(src, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.rstrip("\r\n")
            if not line.lstrip().startswith("#"):
                for name in ref.findall(line):
                    if name not in os.environ:
                        sys.exit(f"conf/spark/spark-defaults.conf, строка {n}: "
                                 f"переменной {name} нет в .env")
                line = ref.sub(lambda m: os.environ[m.group(1)], line)
            lines.append(line)
else:
    print("conf/spark/spark-defaults.conf не найден: каталог lake не подключён",
          file=sys.stderr)

lines += ["", "# строки стенда"] + stand
with open(dst, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
PY
exec /opt/entrypoint.sh "$@"
