# Оформление стенда: метаданные в файле на диске стенда, кеш в памяти.
# Секрет учебный: стенд живёт на машине студента и наружу не смотрит.
import os
SQLALCHEMY_DATABASE_URI = "sqlite:////app/superset_home/superset.db"
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "bigdata-stand")
SQLALCHEMY_TRACK_MODIFICATIONS = False
WTF_CSRF_ENABLED = False
TALISMAN_ENABLED = False
FEATURE_FLAGS = {"ALERT_REPORTS": False}
