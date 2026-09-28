# Потоковый движок с коннекторами курса: брокер, таблицы Iceberg, формат Avro
# из реестра схем. Версия 2.1 — текущая ветка; 1.20 (LTS) вышла из окна
# поддержки к началу семестра. Версии зафиксированы на семестр.
FROM apache/flink:2.1.3-java17
ARG FLINK_VERSION=2.1.3
ARG ICEBERG_VERSION=1.11.0
ARG FLINK_KAFKA_VERSION=5.0.0-2.1
USER root
RUN set -eu; cd /opt/flink/lib; \
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-flink-runtime-2.1/${ICEBERG_VERSION}/iceberg-flink-runtime-2.1-${ICEBERG_VERSION}.jar; \
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar; \
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/flink/flink-sql-connector-kafka/${FLINK_KAFKA_VERSION}/flink-sql-connector-kafka-${FLINK_KAFKA_VERSION}.jar; \
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/flink/flink-sql-avro-confluent-registry/${FLINK_VERSION}/flink-sql-avro-confluent-registry-${FLINK_VERSION}.jar; \
    # Iceberg-коннектор тянет классы Hadoop, в образе Flink их нет
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-client-api/3.3.6/hadoop-client-api-3.3.6.jar; \
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/hadoop/hadoop-client-runtime/3.3.6/hadoop-client-runtime-3.3.6.jar
USER flink
