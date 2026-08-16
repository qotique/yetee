from models.connection import ConnectionConfig


def test_round_trip():
    config = ConnectionConfig(
        id="conn-1",
        protocol="ssh",
        host="example.com",
        port=22,
        username="deploy",
        key_path="/home/deploy/.ssh/id_ed25519",
        remote_economy_dir="/srv/mpmissions/chernarus",
        project_name="My Chernarus",
    )
    restored = ConnectionConfig.from_dict(config.to_dict())
    assert restored == config


def test_round_trip_default_project_name():
    config = ConnectionConfig(
        id="conn-2",
        protocol="ssh",
        host="example.com",
        port=22,
        username="deploy",
    )
    restored = ConnectionConfig.from_dict(config.to_dict())
    assert restored == config
    assert restored.project_name == ""


def test_from_dict_defaults():
    config = ConnectionConfig.from_dict(
        {"id": "x", "protocol": "ftp", "host": "h", "username": "u"}
    )
    assert config.port == 0
    assert config.key_path == ""
    assert config.remote_economy_dir == ""
    assert config.project_name == ""


def test_from_dict_str_coercion():
    config = ConnectionConfig.from_dict(
        {"id": 1, "protocol": 2, "host": "h", "port": "22", "username": "u"}
    )
    assert config.id == "1"
    assert config.protocol == "2"
    assert config.port == 22
