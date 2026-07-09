from src.brief import _extract_tenure


class TestExtractTenure:
    def test_with_signup(self):
        result = _extract_tenure("2020-01-01T00:00:00+00:00")
        assert result["available"] is True
        assert result["years"] is not None

    def test_no_signup(self):
        result = _extract_tenure(None)
        assert result["available"] is False
