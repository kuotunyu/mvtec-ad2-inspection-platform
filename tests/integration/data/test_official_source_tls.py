from __future__ import annotations

from urllib.request import Request, urlopen

import pytest

from experiments.data.download import MVTECAD2_SOURCE, create_tls_context


@pytest.mark.dataset
def test_official_source_tls_range_and_size_are_verifiable() -> None:
    request = Request(MVTECAD2_SOURCE.url, headers={"Range": "bytes=0-0"})

    with urlopen(request, timeout=30, context=create_tls_context()) as response:
        content_range = response.headers["Content-Range"]
        payload = response.read()

    assert response.status == 206
    assert content_range == f"bytes 0-0/{MVTECAD2_SOURCE.expected_size}"
    assert len(payload) == 1
