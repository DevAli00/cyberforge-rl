import cyberforge


def test_version_is_exposed() -> None:
    assert cyberforge.__version__ == "0.1.0"
