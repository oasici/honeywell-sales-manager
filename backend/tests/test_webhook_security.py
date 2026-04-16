"""Tests for SSRF protection in webhook URL validation."""

import pytest

from app.services.webhook_service import validate_webhook_url


class TestValidateWebhookUrlBlocksInternalAddresses:
    """validate_webhook_url must reject URLs pointing to internal/private networks."""

    def test_rejects_localhost(self):
        with pytest.raises(ValueError):
            validate_webhook_url("http://localhost/x")

    def test_rejects_loopback_ip(self):
        with pytest.raises(ValueError):
            validate_webhook_url("http://127.0.0.1/x")

    def test_rejects_private_10_network(self):
        with pytest.raises(ValueError):
            validate_webhook_url("http://10.0.0.1/x")

    def test_rejects_private_172_network(self):
        with pytest.raises(ValueError):
            validate_webhook_url("http://172.16.0.1/x")

    def test_rejects_private_192_network(self):
        with pytest.raises(ValueError):
            validate_webhook_url("http://192.168.1.1/x")

    def test_rejects_link_local_metadata_endpoint(self):
        with pytest.raises(ValueError):
            validate_webhook_url("http://169.254.169.254/latest")

    def test_rejects_file_protocol(self):
        with pytest.raises(ValueError):
            validate_webhook_url("file:///etc/passwd")

    def test_rejects_data_protocol(self):
        with pytest.raises(ValueError):
            validate_webhook_url("data:text/html,hello")

    def test_rejects_empty_string(self):
        with pytest.raises(ValueError):
            validate_webhook_url("")

    def test_rejects_no_hostname(self):
        with pytest.raises(ValueError):
            validate_webhook_url("http:///path")


class TestValidateWebhookUrlAcceptsExternalUrls:
    """validate_webhook_url should accept valid external HTTPS URLs.

    DNS resolution may fail in the test environment for external hostnames,
    so we catch ValueError (raised when hostname cannot be resolved) and
    treat it as acceptable -- the important thing is that the protocol
    and hostname checks pass.
    """

    def test_accepts_valid_external_https_url(self):
        """External HTTPS URL should either pass or fail only on DNS resolution."""
        try:
            validate_webhook_url("https://hooks.example.com/webhook")
        except ValueError as exc:
            # DNS resolution failure is expected in isolated test environments
            assert "cozumlenemedi" in str(exc), (
                f"Expected DNS resolution error, got: {exc}"
            )

    def test_accepts_valid_external_http_url(self):
        """External HTTP URL should either pass or fail only on DNS resolution."""
        try:
            validate_webhook_url("http://hooks.example.com/webhook")
        except ValueError as exc:
            assert "cozumlenemedi" in str(exc), (
                f"Expected DNS resolution error, got: {exc}"
            )

    def test_rejects_ftp_protocol(self):
        with pytest.raises(ValueError, match="protokolu"):
            validate_webhook_url("ftp://example.com/file")

    def test_rejects_javascript_protocol(self):
        with pytest.raises(ValueError, match="protokolu"):
            validate_webhook_url("javascript:alert(1)")
