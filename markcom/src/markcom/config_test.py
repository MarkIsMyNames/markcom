import json
from pathlib import Path

import pytest
from pydantic import HttpUrl

from markcom.config import BaseAppConfig, ConfigError, load_config


class ExampleConfig(BaseAppConfig):
    api_url: HttpUrl
    output_dir: Path
    workers: int


VALID = {
    "log_level": "DEBUG",
    "api_url": "https://api.example.test/",
    "output_dir": "out",
    "workers": 4,
}


def write(tmp_path, content) -> Path:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_loads_typed_values(tmp_path):
    config = load_config(write(tmp_path, VALID), ExampleConfig)
    assert config.log_level == "DEBUG"
    assert config.api_url.host == "api.example.test"
    assert config.output_dir == Path("out")
    assert config.workers == 4


@pytest.mark.parametrize(
    "content",
    [
        {**VALID, "api_url": None},
        {"log_level": "DEBUG", "output_dir": "out", "workers": 4},
        {**VALID, "extra": True},
        {**VALID, "log_level": "LOUD"},
        {**VALID, "workers": "4"},
        {**VALID, "api_url": "not a url"},
    ],
)
def test_rejects_invalid_config(tmp_path, content):
    path = write(tmp_path, content)
    with pytest.raises(ConfigError, match=r"config\.json"):
        load_config(path, ExampleConfig)


def test_rejects_a_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.json", ExampleConfig)


def test_config_is_immutable(tmp_path):
    config = load_config(write(tmp_path, VALID), ExampleConfig)
    with pytest.raises(ValueError, match="frozen"):
        config.workers = 8
