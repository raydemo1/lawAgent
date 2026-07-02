import pytest

from law_agent.data.manifest import build_manifest


def test_manifest_build_requires_real_source() -> None:
    with pytest.raises(ValueError, match="A real source must be selected"):
        build_manifest("data_compliance")
