from sopx.config import DEFAULTS, _deep_merge, ensure_config, get, load_config, save_config


def test_load_config_without_file_returns_defaults(tmp_path):
    config = load_config(tmp_path / "does_not_exist.yaml")
    assert config["language"] == "pt-BR"
    assert config["whisper"]["model_size"] == "base"


def test_load_config_without_file_does_not_mutate_global_defaults(tmp_path):
    config = load_config(tmp_path / "does_not_exist.yaml")
    config["whisper"]["model_size"] = "large-v3"
    assert DEFAULTS["whisper"]["model_size"] == "base"
    # A second, independent load must not see the mutation either.
    config2 = load_config(tmp_path / "does_not_exist2.yaml")
    assert config2["whisper"]["model_size"] == "base"


def test_deep_merge_overrides_nested_keys():
    base = {"whisper": {"model_size": "base"}, "language": "pt-BR"}
    override = {"whisper": {"model_size": "medium"}}
    merged = _deep_merge(base, override)
    assert merged["whisper"]["model_size"] == "medium"
    assert merged["language"] == "pt-BR"


def test_save_and_load_config_roundtrip(tmp_path):
    path = tmp_path / "config.yaml"
    save_config({"language": "en-US"}, path)
    config = load_config(path)
    assert config["language"] == "en-US"
    # Defaults still fill in keys the saved file didn't set.
    assert config["whisper"]["model_size"] == "base"


def test_ensure_config_creates_file_on_first_run(tmp_path):
    path = tmp_path / "config.yaml"
    assert not path.exists()
    config = ensure_config(path)
    assert path.exists()
    assert config["language"] == "pt-BR"


def test_get_dot_notation():
    config = {"whisper": {"model_size": "base"}}
    assert get(config, "whisper.model_size") == "base"
    assert get(config, "whisper.missing", "fallback") == "fallback"
    assert get(config, "not.a.dict.at.all", "fallback") == "fallback"
