# Встраиваемый движок запросов с расширениями курса, установленными заранее:
# на паре сети может не быть. Расширения лежат в домашнем каталоге образа,
# доступном любому пользователю, — контейнер запускается от пользователя
# рабочей машины, чтобы файлы в data/duckdb принадлежали ему.
FROM datacatering/duckdb:v1.5.5
ENV HOME=/home/duckdb
RUN mkdir -p /home/duckdb && /duckdb -c "INSTALL iceberg; INSTALL httpfs; INSTALL avro;" \
    && chmod -R a+rX /home/duckdb
