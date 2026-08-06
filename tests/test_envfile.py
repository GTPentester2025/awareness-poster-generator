from app.envfile import mask, read_env, update_env


def test_read_missing_file(tmp_path):
    assert read_env(tmp_path / "nope.env") == {}


def test_read_parses_and_ignores_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# comment\nA=1\n\nB = two \nBAD_LINE\n", encoding="utf-8")
    assert read_env(p) == {"A": "1", "B": "two"}


def test_update_preserves_other_keys_and_comments(tmp_path):
    p = tmp_path / ".env"
    p.write_text("# header\nA=old\nBASE_URL=http://x\n", encoding="utf-8")
    update_env(p, {"A": "new"})
    env = read_env(p)
    assert env["A"] == "new"
    assert env["BASE_URL"] == "http://x"
    assert p.read_text(encoding="utf-8").startswith("# header")


def test_update_appends_new_key(tmp_path):
    p = tmp_path / ".env"
    p.write_text("A=1\n", encoding="utf-8")
    update_env(p, {"B": "2"})
    assert read_env(p) == {"A": "1", "B": "2"}


def test_update_skips_empty_values(tmp_path):
    p = tmp_path / ".env"
    p.write_text("SECRET=keepme\n", encoding="utf-8")
    update_env(p, {"SECRET": "", "OTHER": "  "})
    assert read_env(p)["SECRET"] == "keepme"
    assert "OTHER" not in read_env(p)


def test_update_creates_file_when_absent(tmp_path):
    p = tmp_path / ".env"
    update_env(p, {"A": "1"})
    assert read_env(p) == {"A": "1"}


def test_mask():
    assert mask("") == ""
    assert mask("ab") == "••"
    assert mask("sk-verysecretkey1234") == "•" * 16 + "1234"
