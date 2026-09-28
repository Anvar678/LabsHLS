"""Первичная настройка Garage через административный API (v2).

Один узел получает раскладку, ключ доступа варианта импортируется, bucket
озера создаётся и открывается ключу. Каждый шаг сначала проверяет, что
делать нечего, поэтому запуск при каждом `up` безопасен.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("GARAGE_ADMIN_URL", "http://s3:9001")
TOKEN = os.environ.get("GARAGE_ADMIN_TOKEN", "stand-admin")
KEY_ID = os.environ["S3_ACCESS_KEY"]
KEY_SECRET = os.environ["S3_SECRET_KEY"]
BUCKET = os.environ["S3_BUCKET"]
CAPACITY = 1_000_000_000_000  # условная ёмкость узла: раскладка одного узла


def call(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def wait_for_api():
    for _ in range(60):
        try:
            status, _ = call("GET", "/v2/GetClusterStatus")
            if status == 200:
                return
        except (urllib.error.URLError, OSError):
            pass
        time.sleep(2)
    sys.exit("garage: административный API не отвечает")


def ensure_layout():
    status, layout = call("GET", "/v2/GetClusterLayout")
    if status != 200:
        sys.exit(f"garage: GetClusterLayout http={status} {layout}")
    if layout.get("roles"):
        print("s3: раскладка узла есть")
        return
    _, cluster = call("GET", "/v2/GetClusterStatus")
    node_id = cluster["nodes"][0]["id"]
    status, out = call("POST", "/v2/UpdateClusterLayout",
                       {"roles": [{"id": node_id, "zone": "stand", "capacity": CAPACITY, "tags": []}]})
    if status != 200:
        sys.exit(f"garage: UpdateClusterLayout http={status} {out}")
    status, out = call("POST", "/v2/ApplyClusterLayout", {"version": layout["version"] + 1})
    if status != 200:
        sys.exit(f"garage: ApplyClusterLayout http={status} {out}")
    print("s3: раскладка узла назначена")


def ensure_key():
    status, _ = call("GET", f"/v2/GetKeyInfo?id={KEY_ID}")
    if status == 200:
        print("s3: ключ доступа есть")
        return
    status, out = call("POST", "/v2/ImportKey",
                       {"accessKeyId": KEY_ID, "secretAccessKey": KEY_SECRET, "name": "student"})
    if status != 200:
        sys.exit(f"garage: ImportKey http={status} {out}")
    print("s3: ключ доступа импортирован")


def ensure_bucket():
    status, info = call("GET", f"/v2/GetBucketInfo?globalAlias={BUCKET}")
    if status != 200:
        status, info = call("POST", "/v2/CreateBucket", {"globalAlias": BUCKET})
        if status != 200:
            sys.exit(f"garage: CreateBucket http={status} {info}")
        print(f"s3: bucket {BUCKET} создан")
    else:
        print(f"s3: bucket {BUCKET} есть")
    if any(k.get("accessKeyId") == KEY_ID and k["permissions"].get("write") for k in info.get("keys", [])):
        return
    status, out = call("POST", "/v2/AllowBucketKey",
                       {"bucketId": info["id"], "accessKeyId": KEY_ID,
                        "permissions": {"read": True, "write": True, "owner": True}})
    if status != 200:
        sys.exit(f"garage: AllowBucketKey http={status} {out}")
    print(f"s3: ключ {KEY_ID} допущен к bucket'у {BUCKET}")


wait_for_api()
ensure_layout()
ensure_key()
ensure_bucket()
