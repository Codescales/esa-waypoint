from src.brief_builder import build_brief


class TestBuildBrief:
    def test_imports(self):
        assert build_brief is not None
