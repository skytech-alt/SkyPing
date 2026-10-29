"""Простые smoke-тесты: проверяем, что файлы не пустые и ключевые строки на месте."""
from pathlib import Path

def test_requirements_exists():
    assert Path("requirements.txt").exists()
    assert "fastapi" in Path("requirements.txt").read_text()

def test_main_has_health():
    src = Path("main.py").read_text()
    assert "/health" in src
    assert "webhook/upptime" in src

def test_index_has_status_url():
    html = Path("index.html").read_text()
    assert "status.json" in html

def test_upptime_has_sites():
    cfg = Path(".upptimerc.yml").read_text()
    assert "gosuslugi.ru" in cfg
    assert "vk.com" in cfg
