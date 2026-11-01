import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.image_url import IMAGE_URL_ERROR, validate_image_url
from app.schemas import ProductoCreate, ProductoPatch


CASES = json.loads((Path(__file__).parents[2] / "docs/contracts/image-url-cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["value"])
def test_image_policy_shared_with_web(case):
    if case["valid"]:
        assert validate_image_url(case["value"]) == case["value"].strip()
        assert ProductoCreate(nombre="Camisa", precio="10.00", imagen_url=case["value"]).imagen_url == case["value"].strip()
        assert ProductoPatch(imagen_url=case["value"]).imagen_url == case["value"].strip()
    else:
        with pytest.raises(ValueError, match=IMAGE_URL_ERROR):
            validate_image_url(case["value"])
        for schema, fields in [(ProductoCreate, {"nombre": "Camisa", "precio": "10.00"}), (ProductoPatch, {})]:
            with pytest.raises(ValidationError):
                schema(**fields, imagen_url=case["value"])


def test_image_is_optional_but_bounds_are_enforced():
    assert validate_image_url(None) is None
    assert ProductoPatch(imagen_url=None).imagen_url is None
    with pytest.raises(ValueError):
        validate_image_url("https://example.com/" + "a" * 2048)
