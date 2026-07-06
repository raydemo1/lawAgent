import pytest
from pydantic import ValidationError

from law_agent.review.schemas import ReviewFacts


def test_review_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        ReviewFacts(extra_field="not allowed")
