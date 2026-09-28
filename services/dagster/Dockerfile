# Оркестратор с пакетным движком в том же образе (см. образ Airflow): конвейеры
# стенда считают агрегаты локальным Spark, кластера у стенда нет.
# `dagster dev` запускает и веб-интерфейс, и демон: без демона расписания и
# сенсоры не срабатывают. Версии всех пакетов, включая транзитивные, — из
# constraints.txt рядом: pip list проверенного образа.
FROM python:3.12.14-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless curl procps \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "$(dirname "$(dirname "$(readlink -f /usr/bin/java)")")" /opt/java
# Каталог JVM зависит от архитектуры (…-amd64, …-arm64): ссылка даёт один путь.
ENV JAVA_HOME=/opt/java
COPY constraints.txt /tmp/constraints.txt
RUN pip install --no-cache-dir --constraint /tmp/constraints.txt \
    "dagster==1.13.24" "dagster-webserver==1.13.24" "dagster-postgres==0.29.24" \
    "pyspark==3.5.9" "clickhouse-connect==1.9.0" "duckdb==1.5.5"
# Встраиваемый движок для шагов конвейера над файлами озера (см. образ Airflow);
# расширения ставятся при сборке — на паре сети может не быть.
RUN python -c "import duckdb; duckdb.sql('INSTALL iceberg; INSTALL httpfs; INSTALL avro')"
ARG ICEBERG_VERSION=1.11.0
RUN set -eu; d=$(python -c "import pyspark,os;print(os.path.join(os.path.dirname(pyspark.__file__),'jars'))"); cd "$d"; \
    base=https://repo1.maven.org/maven2/org/apache/iceberg; \
    curl -fsSLO $base/iceberg-spark-runtime-3.5_2.12/${ICEBERG_VERSION}/iceberg-spark-runtime-3.5_2.12-${ICEBERG_VERSION}.jar; \
    curl -fsSLO $base/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar
COPY dagster.yaml workspace.yaml entrypoint.sh /opt/dagster/
RUN chmod +x /opt/dagster/entrypoint.sh
ENV DAGSTER_HOME=/opt/dagster/home
WORKDIR /opt/dagster/project
ENTRYPOINT ["/opt/dagster/entrypoint.sh"]
CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3000", "-w", "/opt/dagster/workspace.yaml"]
