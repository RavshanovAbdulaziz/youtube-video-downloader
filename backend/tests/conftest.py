"""Test'lar backend modullarini `import downloader` kabi bare-import bilan
topishi uchun — start.bat/tray_app.py ham xuddi shunday ishlaydi.

`APP_DATA_DIR` har bir test sessiyasi uchun vaqtinchalik papkaga qaratiladi:
`paths.py` uni IMPORT PAYTIDA o'qiydi va o'sha yerda papka/config yaratadi,
shuning uchun bu backend modullari import qilinishidan OLDIN bajarilishi
shart — aks holda testlar foydalanuvchining haqiqiy downloads/config
fayllariga tegib ketardi.
"""
import os
import sys
import tempfile

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _BACKEND_DIR)

os.environ["APP_DATA_DIR"] = tempfile.mkdtemp(prefix="ytdl_tests_")
# Testlar tarmoqqa chiqmasligi kerak — bgutil serverini qidirishni ham
# o'chiramiz (aks holda ensure_running() har chaqiruvda kutib turadi).
os.environ["BGUTIL_SERVER_DIR"] = ""
os.environ["YTDLP_POT_BASE_URL"] = ""
