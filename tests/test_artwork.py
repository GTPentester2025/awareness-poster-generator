import base64
from pathlib import Path

import pytest

from app.artwork import generate
from tests.test_content import SETTINGS

PNG_1PX = base64.b64encode(
    bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000d49444154789c626001000000ffff03000006000557bfabd4000000"
        "0049454e44ae426082"
    )
).decode()


class FakeImages:
    def __init__(self, fail=False):
        self.fail = fail
        self.kwargs = None

    def generate(self, **kwargs):
        if self.fail:
            raise RuntimeError("api down")
        self.kwargs = kwargs
        item = type("I", (), {"b64_json": PNG_1PX})
        return type("R", (), {"data": [item]})


class FakeClient:
    def __init__(self, fail=False):
        self.images = FakeImages(fail)


def test_writes_png(tmp_path):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path})
    client = FakeClient()
    p = generate("water drop art", "portrait", s, client=client)
    assert p is not None and p.exists() and p.suffix == ".png"
    assert client.images.kwargs["size"] == "1024x1536"
    assert client.images.kwargs["model"] == "gpt-image-1"


def test_landscape_size(tmp_path):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path})
    client = FakeClient()
    generate("art", "landscape", s, client=client)
    assert client.images.kwargs["size"] == "1536x1024"


def test_api_failure_returns_none(tmp_path):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path})
    assert generate("art", "portrait", s, client=FakeClient(fail=True)) is None


def test_bad_orientation_raises(tmp_path):
    s = SETTINGS.__class__(**{**SETTINGS.__dict__, "out_dir": tmp_path})
    with pytest.raises(ValueError):
        generate("art", "square", s, client=FakeClient())
