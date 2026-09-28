"""Первичная настройка каталога таблиц Lakekeeper: bootstrap и склад варианта.

Склад создаётся над bucket'ом объектного хранилища с учётными данными из .env;
выдача учётных данных клиентам и удалённая подпись выключены — движки ходят в
хранилище своим ключом. Запуск при каждом `up` безопасен: повторный bootstrap
и существующий склад не считаются ошибкой.

Bucket создаёт `s3-init` из файла оси `s3`, который в `compose.yaml` не виден:
зависимость от него сломала бы проект работ 1–3, где файла оси ещё нет. Поэтому
склад создаётся с повтором, пока каталог не примет bucket.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

CATALOG = os.environ.get("CATALOG_URI", "http://catalog:8181/catalog").rsplit("/catalog", 1)[0]
MGMT = CATALOG + "/management/v1"
WAREHOUSE = os.environ.get("CATALOG_WAREHOUSE", "lake")


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(path, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


for _ in range(90):
    try:
        if call("GET", CATALOG + "/health")[0] == 200:
            break
    except (urllib.error.URLError, OSError):
        pass
    time.sleep(2)
else:
    sys.exit("catalog: сервер не отвечает")

status, out = call("POST", MGMT + "/bootstrap", {"accept-terms-of-use": True})
if status in (200, 201, 204):
    print("catalog: bootstrap выполнен")
elif status in (400, 409):
    print("catalog: уже инициализирован")
else:
    sys.exit(f"catalog: bootstrap http={status} {out}")

status, out = call("GET", MGMT + "/warehouse")
if status != 200:
    sys.exit(f"catalog: список складов http={status} {out}")
if any(w.get("name") == WAREHOUSE for w in out.get("warehouses", [])):
    print(f"catalog: склад {WAREHOUSE} есть")
    sys.exit(0)

WAREHOUSE_BODY = {
    "warehouse-name": WAREHOUSE,
    "storage-profile": {
        "type": "s3",
        "bucket": os.environ["S3_BUCKET"],
        "region": os.environ.get("S3_REGION", "stand"),
        "endpoint": os.environ["S3_ENDPOINT"],
        "path-style-access": True,
        "flavor": "s3-compat",
        "sts-enabled": False,
        "remote-signing-enabled": False,
        "push-s3-delete-disabled": False,
    },
    "storage-credential": {
        "type": "s3",
        "credential-type": "access-key",
        "aws-access-key-id": os.environ["S3_ACCESS_KEY"],
        "aws-secret-access-key": os.environ["S3_SECRET_KEY"],
    },
}

for attempt in range(60):
    status, out = call("POST", MGMT + "/warehouse", WAREHOUSE_BODY)
    if status in (200, 201):
        break
    if status == 409:
        print(f"catalog: склад {WAREHOUSE} есть")
        sys.exit(0)
    if attempt == 0:
        print(f"catalog: склад пока не создан (http={status}), ждём bucket {os.environ['S3_BUCKET']}")
    time.sleep(5)
if status not in (200, 201):
    sys.exit(f"catalog: создание склада http={status} {out}")
print(f"catalog: склад {WAREHOUSE} создан над bucket'ом {os.environ['S3_BUCKET']}")
