import unittest

from utils.checker.service import (
    _get_allowed_redirect_target,
    _is_ai_studio_response_usable,
)


class AIStudioAvailabilityTests(unittest.TestCase):
    def test_allows_only_expected_https_redirect_hosts(self):
        self.assertEqual(
            _get_allowed_redirect_target(
                current_url="https://aistudio.google.com/",
                location="https://accounts.google.com/signin/v2/identifier",
            ),
            "https://accounts.google.com/signin/v2/identifier",
        )
        self.assertIsNone(
            _get_allowed_redirect_target(
                current_url="https://aistudio.google.com/",
                location="https://evil.example/redirect",
            )
        )
        self.assertIsNone(
            _get_allowed_redirect_target(
                current_url="https://aistudio.google.com/",
                location="http://accounts.google.com/insecure",
            )
        )

    def test_blocks_available_regions_redirect(self):
        self.assertFalse(
            _is_ai_studio_response_usable(
                status=200,
                visited_urls=[
                    "https://aistudio.google.com/",
                    "https://ai.google.dev/gemini-api/docs/available-regions",
                ],
                body_text="Available regions for Google AI Studio and Gemini API",
            )
        )

    def test_blocks_region_message_in_body(self):
        self.assertFalse(
            _is_ai_studio_response_usable(
                status=200,
                visited_urls=["https://aistudio.google.com/"],
                body_text="Google AI Studio is not available in your region",
            )
        )

    def test_blocks_age_gate_message(self):
        self.assertFalse(
            _is_ai_studio_response_usable(
                status=200,
                visited_urls=["https://aistudio.google.com/"],
                body_text="You do not meet the minimum age requirement (18+)",
            )
        )

    def test_blocks_access_restricted_status(self):
        self.assertFalse(
            _is_ai_studio_response_usable(
                status=403,
                visited_urls=["https://aistudio.google.com/"],
                body_text="",
            )
        )

    def test_accepts_aistudio_page(self):
        self.assertTrue(
            _is_ai_studio_response_usable(
                status=200,
                visited_urls=["https://aistudio.google.com/app/prompts/new_chat"],
                body_text="Google AI Studio",
            )
        )

    def test_accepts_google_login_as_non_blocked_path(self):
        self.assertTrue(
            _is_ai_studio_response_usable(
                status=200,
                visited_urls=[
                    "https://accounts.google.com/signin/v2/identifier?service=wise"
                ],
                body_text="Sign in - Google Accounts",
            )
        )


if __name__ == "__main__":
    unittest.main()
