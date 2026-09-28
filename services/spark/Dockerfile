# Пакетный движок и инструмент обслуживания таблиц Iceberg. Один и тот же образ
# служит всем вариантам: движок оси `engine` отвечает только за запросы.
# Коннекторы брокера и форматов вшиты: на паре сети может не быть.
FROM apache/spark:3.5.9-scala2.12-java17-python3-ubuntu

ARG ICEBERG_VERSION=1.11.0
ARG SPARK_VERSION=3.5.9
USER root
RUN set -eu; \
    cd /opt/spark/jars; \
    base=https://repo1.maven.org/maven2/org/apache/iceberg; \
    curl -fsSLO $base/iceberg-spark-runtime-3.5_2.12/${ICEBERG_VERSION}/iceberg-spark-runtime-3.5_2.12-${ICEBERG_VERSION}.jar; \
    curl -fsSLO $base/iceberg-aws-bundle/${ICEBERG_VERSION}/iceberg-aws-bundle-${ICEBERG_VERSION}.jar; \
    sp=https://repo1.maven.org/maven2/org/apache/spark; \
    curl -fsSLO $sp/spark-sql-kafka-0-10_2.12/${SPARK_VERSION}/spark-sql-kafka-0-10_2.12-${SPARK_VERSION}.jar; \
    curl -fsSLO $sp/spark-token-provider-kafka-0-10_2.12/${SPARK_VERSION}/spark-token-provider-kafka-0-10_2.12-${SPARK_VERSION}.jar; \
    curl -fsSLO $sp/spark-avro_2.12/${SPARK_VERSION}/spark-avro_2.12-${SPARK_VERSION}.jar; \
    curl -fsSLO $sp/spark-protobuf_2.12/${SPARK_VERSION}/spark-protobuf_2.12-${SPARK_VERSION}.jar; \
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/kafka/kafka-clients/3.4.1/kafka-clients-3.4.1.jar; \
    curl -fsSLO https://repo1.maven.org/maven2/org/apache/commons/commons-pool2/2.11.1/commons-pool2-2.11.1.jar; \
    mkdir -p /opt/spark/conf /home/spark/work; \
    chown -R spark:spark /opt/spark/conf /home/spark
COPY entrypoint.sh /opt/stand-entrypoint.sh
RUN chmod +x /opt/stand-entrypoint.sh
USER spark
WORKDIR /home/spark
ENTRYPOINT ["/opt/stand-entrypoint.sh"]
