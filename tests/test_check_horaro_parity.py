from src.check_horaro_parity import main as parity_main


class TestMain:
    def test_imports(self):
        assert parity_main is not None
