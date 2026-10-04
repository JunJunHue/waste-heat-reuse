import pytest

from heattwin.data.cache import FetchError, _validate


def test_html_error_page_is_never_cached_as_json(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("<html><head><title>Missing Key</title></head></html>")
    with pytest.raises(FetchError):
        _validate(p, "json", "https://example.test")


def test_valid_payloads_pass(tmp_path):
    j = tmp_path / "a.json"; j.write_text('[{"a": 1}]')
    z = tmp_path / "a.zip"; z.write_bytes(b"PK\x03\x04rest")
    _validate(j, "json", "u"); _validate(z, "zip", "u")
