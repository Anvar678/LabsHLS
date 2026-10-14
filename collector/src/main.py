# Сборщик событий GH Archive для обязательного задания ЛР1.
# Режим record собирает новые часы, backfill загружает заданную историю.

import contextlib
import fcntl
import gzip
import http.client
import json
import os
import random
import signal
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path


UTC = timezone.utc
ONE_HOUR = timedelta(hours=1)

STOP_REQUESTED = threading.Event()

DOWNLOAD_CHUNK = 64 * 1024
MAX_EVENT_BYTES = 16 * 1024 * 1024
OUTPUT_FILE_BYTES = 64 * 1024 * 1024


def _parse_time(text):
    """Переводит дату в UTC; дата без пояса по контракту означает UTC."""
    value = datetime.fromisoformat(str(text).replace("Z", "+00:00"))

    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)

    return value.astimezone(UTC)


def _time_text(value):
    """Формат времени события: UTC с миллисекундами и окончанием Z."""
    return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _hour_start(value):
    return value.replace(minute=0, second=0, microsecond=0)


def _log(level, message, **details):
    """Печатает одну строку JSON в журнал Docker."""
    record = {
        "ts": _time_text(datetime.now(UTC)),
        "level": level,
        "msg": message,
        **details,
    }

    print(json.dumps(record, ensure_ascii=False), flush=True)


def _request_stop(signum, frame):
    STOP_REQUESTED.set()


def _check_stop():
    if STOP_REQUESTED.is_set():
        raise InterruptedError("Сборщик остановлен")


def _required_setting(name):
    value = os.environ.get(name, "").strip()

    if not value:
        raise ValueError(f"Не задана переменная {name}")

    return value


def _read_settings(mode):
    """Docker передаёт настройки через окружение; сам файл .env не читается."""
    raw_dir = Path(os.environ.get("COLLECTOR_RAW_DIR", "/data/raw")).resolve()
    output_dir = raw_dir / ("stream" if mode == "record" else "history")

    settings = {
        "mode": mode,
        "raw_dir": raw_dir,
        "output_dir": Path(os.environ.get("COLLECTOR_OUT_DIR", str(output_dir))).resolve(),
        "state_dir": raw_dir / "state",
        "source": _required_setting("SOURCE"),
        "event_types": set(_required_setting("SOURCE_FILTER").split(",")),
        "base_url": _required_setting("COLLECTOR_BASE_URL").rstrip("/"),
        "user_agent": _required_setting("COLLECTOR_USER_AGENT"),
        "limit_bytes": int(float(os.environ.get("COLLECTOR_RAW_LIMIT_GB", "20")) * 1_000_000_000),
        "poll_seconds": float(os.environ.get("COLLECTOR_POLL_SECONDS", "60")),
        "http_timeout": float(os.environ.get("COLLECTOR_HTTP_TIMEOUT", "60")),
        "min_size_ratio": float(os.environ.get("COLLECTOR_MIN_SIZE_RATIO", "0.2")),
    }

    if settings["source"] != "github" or settings["output_dir"] != output_dir:
        raise ValueError("Нужны SOURCE=github и стандартный каталог stream или history")

    if not settings["base_url"].startswith(("https://", "http://")):
        raise ValueError("COLLECTOR_BASE_URL должен начинаться с https:// или http://")

    settings["event_types"] = {
        value.strip()
        for value in settings["event_types"]
        if value.strip()
    }

    if not settings["event_types"] or settings["limit_bytes"] <= 0 or settings["poll_seconds"] < 1:
        raise ValueError("Проверь SOURCE_FILTER, COLLECTOR_RAW_LIMIT_GB и COLLECTOR_POLL_SECONDS")

    if settings["http_timeout"] <= 0 or not 0 <= settings["min_size_ratio"] < 1:
        raise ValueError("Недопустимый таймаут или порог размера архива")

    settings["work_dir"] = settings["state_dir"] / "work"
    settings["work_dir"].mkdir(parents=True, exist_ok=True)
    settings["output_dir"].mkdir(parents=True, exist_ok=True)

    return settings


@contextlib.contextmanager
def _exclusive_access(settings):
    """Пока обрабатывается час, второй экземпляр ждёт и не трогает его файлы."""
    with open(settings["state_dir"] / "collector.lock", "a+b") as lock_file:
        while True:
            _check_stop()

            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                STOP_REQUESTED.wait(0.2)

        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _open_state_database(settings):
    """SQLite хранит ключи на диске, чтобы не держать всю историю в памяти."""
    database = sqlite3.connect(
        settings["state_dir"] / "collector.sqlite3",
        isolation_level=None,
        timeout=60,
    )

    database.executescript("""
        PRAGMA synchronous=FULL;
        PRAGMA cache_size=-8192;

        CREATE TABLE IF NOT EXISTS meta (
            name TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY
        );

        CREATE TABLE IF NOT EXISTS seen (
            event_key TEXT PRIMARY KEY,
            path TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS seen_path ON seen(path);

        CREATE TABLE IF NOT EXISTS archives (
            mode TEXT,
            hour TEXT,
            size INTEGER NOT NULL,
            PRIMARY KEY (mode, hour)
        );
    """)

    return database


def _read_state(database, name):
    row = database.execute("SELECT value FROM meta WHERE name=?", (name,)).fetchone()
    return row[0] if row else None


def _save_state(database, name, value):
    database.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (name, str(value)))


def _closed_files(settings):
    """В предел хранения входят только готовые файлы stream и history."""
    return [
        path
        for layer in ("stream", "history")
        for path in (settings["raw_dir"] / layer).rglob("*.jsonl.gz")
    ]


def _remove_file_index(database, path):
    database.execute("DELETE FROM seen WHERE path=?", (str(path),))
    database.execute("DELETE FROM files WHERE path=?", (str(path),))


def _restore_file_index(settings, database):
    """После сбоя подбирает файлы, записанные до сохранения позиции."""

    # --- Переход со старой версии: перестраиваем только индекс, данные сохраняем ---
    if _read_state(database, "index_format") != "per-layer-v1":
        database.execute("BEGIN")
        database.execute("DELETE FROM seen")
        database.execute("DELETE FROM files")
        _save_state(database, "index_format", "per-layer-v1")
        database.commit()

    actual_files = {str(path): path for path in _closed_files(settings)}
    indexed_files = {row[0] for row in database.execute("SELECT path FROM files")}

    for name in indexed_files - actual_files.keys():
        database.execute("BEGIN")
        _remove_file_index(database, name)
        database.commit()

    # --- Готовый файл является доказательством, что события уже сохранены ---
    for name in actual_files.keys() - indexed_files:
        path = actual_files[name]
        mode = "record" if path.is_relative_to(settings["raw_dir"] / "stream") else "backfill"

        database.execute("BEGIN")

        try:
            with gzip.open(path, "rb") as saved_file:
                while True:
                    _check_stop()
                    line = saved_file.readline(MAX_EVENT_BYTES + 1)

                    if not line:
                        break

                    if len(line) > MAX_EVENT_BYTES:
                        raise ValueError("Строка сохранённого файла больше 16 МиБ")

                    event = json.loads(line)
                    key = f"{mode}:{event['event_key']}"

                    database.execute(
                        "INSERT OR IGNORE INTO seen VALUES (?, ?)",
                        (key, name),
                    )

            database.execute("INSERT INTO files VALUES (?)", (name,))
            database.commit()
            _log("info", "recovered", file=name)

        except BaseException:
            database.rollback()
            raise

    # --- Незакрытые временные файлы пересоздаются повторной загрузкой часа ---
    for path in settings["work_dir"].glob("*.part"):
        path.unlink()


def _enforce_storage_limit(settings, database, incoming_bytes=0):
    """Освобождает место, удаляя самые старые партиции и файлы внутри них."""
    if incoming_bytes > settings["limit_bytes"]:
        raise ValueError("Один отфильтрованный час превышает весь предел хранения")

    files = _closed_files(settings)
    total_bytes = sum(path.stat().st_size for path in files)

    files.sort(key=lambda path: (
        next(part for part in path.parts if part.startswith("dt=")),
        path.stat().st_mtime,
    ))

    for path in files:
        if total_bytes + incoming_bytes <= settings["limit_bytes"]:
            break

        size = path.stat().st_size
        path.unlink()
        _remove_file_index(database, path)
        total_bytes -= size

        _log("info", "rotated", file=str(path), bytes=size)


def _open_archive_request(settings, archive_hour, method="GET"):
    """Имя архива GH Archive содержит час без ведущего нуля."""
    _check_stop()

    url = f"{settings['base_url']}/{archive_hour:%Y-%m-%d}-{archive_hour.hour}.json.gz"
    headers = {
        "User-Agent": settings["user_agent"],
        "Accept-Encoding": "identity",
    }

    request = urllib.request.Request(url, headers=headers, method=method)
    return urllib.request.urlopen(request, timeout=settings["http_timeout"])


def _download_archive(settings, database, archive_hour):
    """Сохраняет сжатый архив на диск небольшими кусками, проверяет размер."""
    temporary_path = settings["work_dir"] / "download.part"
    downloaded_bytes = 0

    _log("info", "download_started", archive_hour=_time_text(archive_hour))

    with _open_archive_request(settings, archive_hour) as response, open(temporary_path, "wb") as target:
        expected_size = response.headers.get("Content-Length")

        while True:
            _check_stop()
            chunk = response.read(DOWNLOAD_CHUNK)

            if not chunk:
                break

            target.write(chunk)
            downloaded_bytes += len(chunk)

    if downloaded_bytes == 0 or (expected_size is not None and downloaded_bytes != int(expected_size)):
        raise ValueError("Архив пуст или скачан не полностью")

    # --- Подозрительно маленький час сравниваем с предыдущим часом ---
    previous = database.execute(
        "SELECT size FROM archives WHERE hour=? LIMIT 1",
        (_time_text(archive_hour - ONE_HOUR),),
    ).fetchone()

    previous_size = previous[0] if previous else 0

    if not previous_size and settings["min_size_ratio"]:
        STOP_REQUESTED.wait(1)

        try:
            with _open_archive_request(settings, archive_hour - ONE_HOUR, "HEAD") as response:
                previous_size = int(response.headers.get("Content-Length", "0"))

        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise

    if previous_size and downloaded_bytes < previous_size * settings["min_size_ratio"]:
        raise ValueError(
            f"Подозрительно маленький архив: {downloaded_bytes} байт; "
            f"предыдущий: {previous_size}"
        )

    _log("info", "download_finished", archive_hour=_time_text(archive_hour), bytes=downloaded_bytes)

    return temporary_path, downloaded_bytes


def _close_output_file(writer):
    """Закрывает gzip и отправляет его содержимое из буфера на диск."""
    if writer["file"] is not None:
        writer["file"].close()

        with open(writer["paths"][-1][0], "rb") as saved_file:
            os.fsync(saved_file.fileno())

        writer["file"] = None


def _write_event(settings, database, writer, event, received_at):
    """Выбирает партицию и пишет одно событие во временный gzip-файл."""
    if settings["mode"] == "record":
        partition = f"dt={received_at:%Y-%m-%d}/hour={received_at:%H}"
    else:
        partition = f"dt={event['event_time'][:10]}"

    if writer["file"] is None or writer["partition"] != partition or writer["bytes"] >= OUTPUT_FILE_BYTES:
        _close_output_file(writer)

        name = f"gh-{writer['archive_hour']:%Y%m%dT%H}-{uuid.uuid4().hex}.jsonl.gz"
        final_path = settings["output_dir"] / partition / name
        temporary_path = settings["work_dir"] / (name + ".part")

        writer["paths"].append((temporary_path, final_path))
        writer["file"] = gzip.open(temporary_path, "wb", compresslevel=6)
        writer["partition"], writer["bytes"] = partition, 0

        database.execute("INSERT INTO files VALUES (?)", (str(final_path),))

    line = (json.dumps(event, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

    if len(line) > MAX_EVENT_BYTES:
        raise ValueError("Сохранённое событие больше 16 МиБ")

    writer["file"].write(line)
    writer["bytes"] += len(line)

    key = f"{settings['mode']}:{event['event_key']}"
    database.execute("INSERT INTO seen VALUES (?, ?)", (key, str(writer["paths"][-1][1])))

    return len(line)


def _process_archive(settings, database, archive_hour):
    """Выполняет весь цикл одного часа: скачать, отфильтровать, записать, сохранить позицию."""
    archive_path, archive_bytes = _download_archive(settings, database, archive_hour)

    writer = {
        "file": None,
        "partition": None,
        "bytes": 0,
        "paths": [],
        "archive_hour": archive_hour,
    }

    received_count = 0
    selected_count = 0
    saved_count = 0
    duplicate_count = 0
    source_bytes = 0
    saved_bytes = 0

    database.execute("BEGIN")

    try:
        # --- Чтение по строке: весь распакованный архив не попадает в память ---
        with gzip.open(archive_path, "rb") as archive:
            while True:
                _check_stop()
                line = archive.readline(MAX_EVENT_BYTES + 1)

                if not line:
                    break

                if len(line) > MAX_EVENT_BYTES:
                    raise ValueError("Одно событие больше 16 МиБ")

                source_bytes += len(line)

                if not line.strip():
                    continue

                event = json.loads(line)

                if not isinstance(event, dict):
                    raise ValueError("Событие должно быть JSON-объектом")

                received_count += 1

                if event.get("type") not in settings["event_types"]:
                    continue

                selected_count += 1

                if not event.get("id") or not event.get("created_at"):
                    raise ValueError("У события из фильтра нет id или created_at")

                # --- Повторы исключаются отдельно внутри потока и внутри истории ---
                event_key = str(event["id"])
                index_key = f"{settings['mode']}:{event_key}"

                if database.execute("SELECT 1 FROM seen WHERE event_key=?", (index_key,)).fetchone():
                    duplicate_count += 1
                    continue

                received_at = datetime.now(UTC)

                event["event_key"] = event_key
                event["event_time"] = _time_text(_parse_time(event["created_at"]))
                event["received_at"] = _time_text(received_at)
                event["source"] = settings["source"]

                saved_bytes += _write_event(settings, database, writer, event, received_at)
                saved_count += 1

        if received_count == 0:
            raise ValueError("Архив не содержит событий")

        # --- До этой точки gzip проверен до конца, включая контрольную сумму ---
        _close_output_file(writer)

        compressed_bytes = sum(path.stat().st_size for path, _ in writer["paths"])

        _check_stop()
        _enforce_storage_limit(settings, database, compressed_bytes)

        for temporary_path, final_path in writer["paths"]:
            final_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(temporary_path, final_path)

            directory = os.open(final_path.parent, os.O_RDONLY)

            try:
                os.fsync(directory)
            finally:
                os.close(directory)

        # --- Позиция меняется только после закрытия и публикации файлов ---
        database.execute(
            "INSERT OR REPLACE INTO archives VALUES (?, ?, ?)",
            (settings["mode"], _time_text(archive_hour), archive_bytes),
        )

        if settings["mode"] == "record":
            _save_state(database, "record_next", _time_text(archive_hour + ONE_HOUR))

        database.commit()

    except BaseException:
        database.rollback()
        raise

    finally:
        _close_output_file(writer)

        for path in settings["work_dir"].glob("*.part"):
            path.unlink()

    _log(
        "info",
        "poll",
        mode=settings["mode"],
        archive_hour=_time_text(archive_hour),
        got=received_count,
        kept=selected_count,
        written=saved_count,
        duplicates=duplicate_count,
        events_per_minute_before=received_count / 60,
        events_per_minute_after=selected_count / 60,
        bytes_before_filter=source_bytes,
        bytes_after_filter=saved_bytes,
        compressed_before_filter=archive_bytes,
        compressed_after_filter=compressed_bytes,
    )

    _log(
        "info",
        "closed",
        archive_hour=_time_text(archive_hour),
        lines=saved_count,
        files=len(writer["paths"]),
    )

    return saved_count


def _choose_period(settings, database):
    """История: [FROM, TO). Поток: следующий ещё не обработанный час."""
    if settings["mode"] == "record":
        next_hour = _read_state(database, "record_next")

        if next_hour is None:
            next_hour = _time_text(_hour_start(datetime.now(UTC)))
            _save_state(database, "record_next", next_hour)

        return _parse_time(next_hour), None

    start = _parse_time(_required_setting("COLLECTOR_HISTORY_FROM"))
    end = _parse_time(_required_setting("COLLECTOR_HISTORY_TO"))

    if start != _hour_start(start) or end != _hour_start(end) or start >= end or end > _hour_start(datetime.now(UTC)):
        raise ValueError("Нужны границы истории по часу UTC: FROM < TO, TO не в будущем")

    if _read_state(database, "record_next") is None:
        _save_state(database, "record_next", _time_text(end))

    return start, end


def _retry_delay(settings, error, attempt):
    """Пауза растёт при ошибках; указание Retry-After источника имеет приоритет."""
    base = settings["poll_seconds"] if isinstance(error, ValueError) or getattr(error, "code", None) == 404 else 1
    delay = min(600, base * 2 ** min(attempt - 1, 10))

    if isinstance(error, urllib.error.HTTPError):
        value = error.headers.get("Retry-After")

        if value:
            try:
                source_delay = float(value)

            except ValueError:
                try:
                    source_delay = (
                        parsedate_to_datetime(value).astimezone(UTC) - datetime.now(UTC)
                    ).total_seconds()

                except (ValueError, TypeError):
                    source_delay = 0

            delay = max(delay, source_delay)

    return delay + random.random()


def _run_collection(settings, database, archive_hour, end_hour):
    """Повторяет цикл часов; при ошибке остаётся на том же часе."""
    attempt = 0

    while not STOP_REQUESTED.is_set() and (end_hour is None or archive_hour < end_hour):
        if archive_hour + ONE_HOUR > datetime.now(UTC):
            STOP_REQUESTED.wait(settings["poll_seconds"])
            continue

        try:
            with _exclusive_access(settings):
                _restore_file_index(settings, database)

                if settings["mode"] == "record":
                    archive_hour = _parse_time(_read_state(database, "record_next"))

                    if archive_hour + ONE_HOUR > datetime.now(UTC):
                        continue

                completed = database.execute(
                    "SELECT 1 FROM archives WHERE mode=? AND hour=?",
                    (settings["mode"], _time_text(archive_hour)),
                ).fetchone()

                if not completed:
                    _process_archive(settings, database, archive_hour)

            archive_hour += ONE_HOUR
            attempt = 0
            STOP_REQUESTED.wait(1)

        except InterruptedError:
            break

        except (OSError, EOFError, ValueError, sqlite3.Error, urllib.error.URLError, http.client.HTTPException) as error:
            database.rollback()
            attempt += 1
            pause = _retry_delay(settings, error, attempt)

            _log(
                "warn",
                "retry",
                archive_hour=_time_text(archive_hour),
                attempt=attempt,
                status=getattr(error, "code", None),
                reason=str(error),
                pause=round(pause, 2),
            )

            STOP_REQUESTED.wait(pause)

    _log(
        "info",
        "stop",
        mode=settings["mode"],
        completed=end_hour is not None and archive_hour >= end_hour,
    )


def main():
    """Готовит настройки и состояние, затем запускает обработку часов."""
    mode = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("COLLECTOR_MODE", "record")

    if mode not in ("record", "backfill"):
        raise ValueError("В ЛР1 используются только record и backfill")

    settings = _read_settings(mode)

    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)

    database = _open_state_database(settings)

    try:
        with _exclusive_access(settings):
            signature = json.dumps([settings["source"], sorted(settings["event_types"])])
            previous_signature = _read_state(database, "signature")

            if previous_signature and previous_signature != signature:
                raise ValueError("Источник или фильтр изменён относительно сохранённого состояния")

            _save_state(database, "signature", signature)

            _restore_file_index(settings, database)
            _enforce_storage_limit(settings, database)

            archive_hour, end_hour = _choose_period(settings, database)

        _log(
            "info",
            "start",
            mode=mode,
            from_hour=_time_text(archive_hour),
            to_hour=_time_text(end_hour) if end_hour else None,
        )

        _run_collection(settings, database, archive_hour, end_hour)

    finally:
        database.close()


if __name__ == "__main__":
    try:
        main()

    except InterruptedError:
        pass

    except Exception as error:
        _log("error", "fatal", reason=str(error))
        sys.exit(1)
