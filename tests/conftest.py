from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    markexpr = config.option.markexpr
    skip_verify = pytest.mark.skip(reason="run with -m verify for 84000.org network tests")
    skip_corpus = pytest.mark.skip(reason="run with -m corpus for heavy corpus-bootstrap tests")
    for item in items:
        if "verify" in item.keywords and "verify" not in markexpr:
            item.add_marker(skip_verify)
        if "corpus" in item.keywords and "corpus" not in markexpr:
            item.add_marker(skip_corpus)
