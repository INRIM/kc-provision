from kc_provision import is_configured
from kc_provision import patch_dotenv
from kc_provision import read_dotenv_keys


def test_patch_updates_existing_and_appends_new(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# header\nFOO=old\nBAR=keep\n# comment\n", encoding="utf-8")
    patch_dotenv(str(f), {"FOO": "new", "BAZ": "added"})
    text = f.read_text(encoding="utf-8")
    assert "FOO=new" in text
    assert "BAR=keep" in text
    assert "BAZ=added" in text
    assert "# header" in text
    assert "# comment" in text
    assert text.count("FOO=") == 1


def test_patch_creates_file_when_missing(tmp_path):
    f = tmp_path / ".env"
    patch_dotenv(str(f), {"KEY": "val"})
    assert f.read_text(encoding="utf-8").strip() == "KEY=val"


def test_patch_does_not_touch_commented_key(tmp_path):
    f = tmp_path / ".env"
    f.write_text("#FOO=commented\n", encoding="utf-8")
    patch_dotenv(str(f), {"FOO": "real"})
    text = f.read_text(encoding="utf-8")
    assert "#FOO=commented" in text
    assert "FOO=real" in text


def test_read_keys_ignores_comments_and_blanks(tmp_path):
    f = tmp_path / ".env"
    f.write_text("# c\n\nA=1\nB=2\n", encoding="utf-8")
    assert read_dotenv_keys(str(f)) == {"A": "1", "B": "2"}


def test_is_configured():
    values = {"A": "x", "B": "", "C": '""', "D": "'  '"}
    assert is_configured(values, "A") is True
    assert is_configured(values, "B") is False
    assert is_configured(values, "C") is False
    assert is_configured(values, "MISSING") is False
