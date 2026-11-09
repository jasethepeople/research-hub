from pathlib import Path

DASHBOARD_HTML = Path(__file__).with_name("index.html").read_text(encoding="utf-8")
