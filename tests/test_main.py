import datetime
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
import main


class MainHelpersTests(unittest.TestCase):
    def test_endpoint_validation(self):
        self.assertEqual(main.validate_endpoint("https://ollama.example/"), "https://ollama.example")
        with self.assertRaises(ValueError):
            main.validate_endpoint("ollama.example:11434")
        with self.assertRaises(ValueError):
            main.validate_endpoint("https://user:password@ollama.example")
        with self.assertRaises(ValueError):
            main.validate_endpoint("http://ollama.example", enterprise=True)

    def test_payload_variation(self):
        self.assertEqual(main.apply_payload_variation(" payload ", 0), "payload")
        self.assertIn("HYPOTHETICAL_SIMULATION_MODE", main.apply_payload_variation("payload", 1))
        self.assertIn("SANDBOX_REFACTORING_REQUEST", main.apply_payload_variation("payload", 2))
        self.assertIn("%20", main.apply_payload_variation("payload with spaces", 4, choose=lambda tactics: tactics[4]))

    def test_utc_default_is_timezone_aware(self):
        value = main.utc_now()
        self.assertIsInstance(value, datetime.datetime)
        self.assertIsNotNone(value.tzinfo)
        self.assertEqual(value.utcoffset(), datetime.timedelta(0))

    def test_telemetry_model_name(self):
        self.assertEqual(main.LocalVulnerabilityTelemetry.__tablename__, "vulnerability_telemetry")

    def test_supported_byok_providers(self):
        for provider in ("ollama", "anthropic", "openai", "nvidia", "google", "genai", "groq"):
            self.assertEqual(main.normalize_provider(provider), provider)
        with self.assertRaises(ValueError):
            main.normalize_provider("unknown-provider")


if __name__ == "__main__":
    unittest.main()
