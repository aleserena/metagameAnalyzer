from pathlib import Path

from src.mtgtop8.storage import load_json, save_json


def test_save_and_load_json_roundtrip(tmp_path):
    path = tmp_path / "data.json"
    data = {"a": 1, "b": "x"}
    save_json(path, data)
    loaded = load_json(path)
    assert loaded == data


def test_load_json_missing_returns_default(tmp_path):
    path = tmp_path / "missing.json"
    default = {"foo": "bar"}
    loaded = load_json(path, default=default)
    assert loaded == default

