# Оркестратор с пакетным движком в том же образе: конвейеры стенда считают
# агрегаты локальным Spark, кластера у стенда нет. Версии всех пакетов, включая
# транзитивные, — из constraints.txt рядом: pip list проверенного образа.
FROM apache/airflow:3.3.2-python3.12
USER root
RUN apt-get update && apt-get install -y --no-install-recommends openjdk-17-jre-headless curl \
    && rm -rf /var/lib/apt/lists/* \
    && ln -s "$(dirname "$(dirname "$(readlink -f /usr/bin/java)")")" /opt/java
# Каталог JVM зависит от архитектуры (…-amd64, …-arm64): ссылка даёт один путь.
ENV JAVA_HOME=/opt/java
USER airflow
COPY constraints.txt /tmp/constraints.txt
RUN pip install --no-cache-dir --constraint /tmp/constraints.txt \
    "pyspark==3.5.9" "clickhouse-connect==1.9.0" "duckdb==1.5.5" \
    "apache-airflow-providers-standard==1.19.0"
# Встраиваемый движок для шагов конвейера над файлами озера (очистка слоя сырых
# данных, загрузка в таблицу Iceberg): Spark стенда видит объектное хранилище
# только через таблицы. Расширения ставятся при сборке — на паре сети может не быть.
RUN python -c "import duckdb; duckdb.sql('INSTALL iceberg; INSTALL httpfs; INSTALL avro')"
ARG ICEBERG_VERSION=1.11.0
USER root
RUN set -eu; d=$(python -c "import pyspark,os;print(os.path.join(os.path.dirname(pyspark.__file__),'jars'))"); cd "$d"; \
    base=https://repo1.maven.org/maven2/org/apache/iceberg; \
    curl -fsSLO $base/iceberg-spark-runtime-3.5_2.12/${ICEBERG_VERSION}/iceberg-spark-runtime-3.5_2.12-${ICEBERG_VERSION}.jar; \
    curl -fsSLO $base/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar
USER airflow
ENV AWS_REQUEST_CHECKSUM_CALCULATION=when_required AWS_RESPONSE_CHECKSUM_VALIDATION=when_required
