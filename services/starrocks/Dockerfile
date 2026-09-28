# Аналитическая СУБД в одном контейнере. Пределы памяти узлов подобраны под
# стенд, а не под кластер: куча управляющего узла 1,5 ГиБ вместо 8 ГиБ по
# умолчанию, узел хранения — 3 ГиБ вместо 90 % памяти контейнера.
# Конфигурация правится в образе: точка входа образа пишет в conf/, и
# смонтированный только для чтения файл ломает запуск.
FROM starrocks/allin1-ubuntu:3.5.21
RUN set -eu; \
    sed -i 's/-Xmx[0-9]*[mg]/-Xmx1500m/' /data/deploy/starrocks/fe/conf/fe.conf; \
    grep -q 'Xmx1500m' /data/deploy/starrocks/fe/conf/fe.conf; \
    printf '\n# стенд курса: предел памяти узла хранения\nmem_limit = 3G\n' >> /data/deploy/starrocks/be/conf/be.conf
