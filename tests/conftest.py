from __future__ import annotations

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    markexpr = config.option.markexpr
    skip_verify = pytest.mark.skip(reason="run with -m verify for 84000.org network tests")
    for item in items:
        if "verify" in item.keywords and "verify" not in markexpr:
            item.add_marker(skip_verify)
