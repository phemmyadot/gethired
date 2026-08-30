import os
import unittest
from unittest.mock import patch


class TestLLMProvider(unittest.TestCase):
    def test_local_provider_used_by_default(self):
        os.environ.pop("LLM_PROVIDER", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)

        from src.llm import generate_text

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        with patch("src.llm.httpx.post", return_value=FakeResp({
            "choices": [{"message": {"content": "hello"}}]
        })) as post_mock:
            result = generate_text("hi")
            self.assertEqual(result, "hello")
            self.assertTrue(post_mock.called)

    def test_anthropic_fallback_works_when_local_fails(self):
        os.environ["LLM_PROVIDER"] = "local"
        os.environ["ANTHROPIC_API_KEY"] = "test-key"

        from src.llm import generate_text

        class FakeResp:
            def __init__(self, payload):
                self._payload = payload

            def raise_for_status(self):
                return None

            def json(self):
                return self._payload

        with patch("src.llm.httpx.post", side_effect=RuntimeError("offline")):
            with patch("src.llm.call_anthropic", return_value="fallback") as anthropic_mock:
                result = generate_text("hi")
                self.assertEqual(result, "fallback")
                self.assertTrue(anthropic_mock.called)


if __name__ == "__main__":
    unittest.main()
