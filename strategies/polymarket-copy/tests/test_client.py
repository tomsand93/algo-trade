"""
Tests for base HTTP client with retry logic.
"""

from unittest.mock import MagicMock, Mock, patch

import pytest
import httpx

from pmirror.data import (
    ApiClientError,
    BaseHttpClient,
    HttpClientError,
    RateLimitError,
)


class TestBaseHttpClient:
    """Tests for BaseHttpClient."""

    def test_create_client(self):
        """Should create client with base URL."""
        client = BaseHttpClient("https://api.example.com")
        assert client.base_url == "https://api.example.com"
        assert client.max_retries >= 0
        assert client.request_timeout > 0
        client.close()

    def test_base_url_normalized(self):
        """Should strip trailing slashes from base URL."""
        client = BaseHttpClient("https://api.example.com/")
        assert client.base_url == "https://api.example.com"
        client.close()

    def test_context_manager(self):
        """Should work as context manager."""
        with BaseHttpClient("https://api.example.com") as client:
            assert client.base_url == "https://api.example.com"

    @patch("pmirror.data.client.httpx.Client")
    def test_successful_get_request(self, mock_client_class):
        """Should make successful GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"result": "success"}

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        response = client.get("/test")

        assert response.status_code == 200
        mock_client.request.assert_called_once()
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["method"] == "GET"
        assert "https://api.example.com/test" in call_kwargs["url"]
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_successful_get_json(self, mock_client_class):
        """Should parse JSON from GET request."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"data": "value"}

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        data = client.get_json("/test")

        assert data == {"data": "value"}
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_post_request_with_json(self, mock_client_class):
        """Should make POST request with JSON body."""
        mock_response = Mock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"id": 123}

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        data = client.post_json("/create", json_data={"name": "test"})

        assert data == {"id": 123}
        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["method"] == "POST"
        assert call_kwargs["json"] == {"name": "test"}
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_retry_on_500_error(self, mock_client_class):
        """Should retry on server errors."""
        mock_error = Mock(status_code=500)
        mock_error.headers = Mock(get=lambda x: None)

        mock_success = Mock(status_code=200, json=lambda: {"result": "ok"})
        mock_success.headers = Mock(get=lambda x: None)

        mock_client = Mock()
        mock_client.request.side_effect = [mock_error, mock_success]
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        response = client.get("/test")

        assert response.status_code == 200
        assert mock_client.request.call_count == 2
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_retry_on_429_rate_limit(self, mock_client_class):
        """Should retry on rate limit (429)."""
        mock_rate_limit = Mock(status_code=429, headers={})
        mock_success = Mock(status_code=200, json=lambda: {"result": "ok"})
        mock_success.headers = {}

        mock_client = Mock()
        mock_client.request.side_effect = [mock_rate_limit, mock_success]
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        response = client.get("/test")

        assert response.status_code == 200
        assert mock_client.request.call_count == 2
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_retry_after_header_respected(self, mock_client_class):
        """Should use Retry-After header when provided."""
        mock_rate_limit = Mock(status_code=429, headers={"Retry-After": "2"})
        mock_success = Mock(status_code=200, json=lambda: {"result": "ok"})
        mock_success.headers = {}

        mock_client = Mock()
        mock_client.request.side_effect = [mock_rate_limit, mock_success]
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        client.get("/test")

        # Should have used 2 second delay from header
        # We can't directly verify the delay, but we can check the call count
        assert mock_client.request.call_count == 2
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_max_retries_exceeded_rate_limit(self, mock_client_class):
        """Should raise RateLimitError after max retries on 429."""
        mock_rate_limit = Mock(status_code=429, headers={})

        mock_client = Mock()
        mock_client.request.return_value = mock_rate_limit
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        # Reduce retries for faster test
        client.max_retries = 1

        with pytest.raises(RateLimitError) as exc_info:
            client.get("/test")

        assert exc_info.value.status_code == 429
        assert "Rate limit exceeded" in str(exc_info.value)
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_max_retries_exceeded_server_error(self, mock_client_class):
        """Should raise HttpClientError after max retries on 500."""
        mock_error = Mock(status_code=500)
        mock_error.headers = Mock(get=lambda x: None)

        mock_client = Mock()
        mock_client.request.return_value = mock_error
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        client.max_retries = 1

        with pytest.raises(HttpClientError) as exc_info:
            client.get("/test")

        assert "failed after" in str(exc_info.value)
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_4xx_client_error_no_retry(self, mock_client_class):
        """Should not retry on 4xx client errors (except 429)."""
        mock_response = Mock(status_code=400, headers={})

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")

        with pytest.raises(ApiClientError) as exc_info:
            client.get("/test")

        assert exc_info.value.status_code == 400
        # Should only be called once (no retries)
        assert mock_client.request.call_count == 1
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_404_error_no_retry(self, mock_client_class):
        """Should not retry on 404 errors."""
        mock_response = Mock(status_code=404, headers={})

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")

        with pytest.raises(ApiClientError) as exc_info:
            client.get("/notfound")

        assert exc_info.value.status_code == 404
        assert mock_client.request.call_count == 1
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_timeout_retry(self, mock_client_class):
        """Should retry on timeout exceptions."""
        mock_timeout = httpx.TimeoutException("Request timed out")
        mock_success = Mock(status_code=200, json=lambda: {"result": "ok"})
        mock_success.headers = {}

        mock_client = Mock()
        mock_client.request.side_effect = [mock_timeout, mock_success]
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        response = client.get("/test")

        assert response.status_code == 200
        assert mock_client.request.call_count == 2
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_timeout_max_retries(self, mock_client_class):
        """Should raise error after max timeout retries."""
        mock_timeout = httpx.TimeoutException("Request timed out")

        mock_client = Mock()
        mock_client.request.side_effect = mock_timeout
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        client.max_retries = 1

        with pytest.raises(HttpClientError) as exc_info:
            client.get("/test")

        assert "timed out" in str(exc_info.value).lower()
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_network_error_retry(self, mock_client_class):
        """Should retry on network errors."""
        mock_network = httpx.NetworkError("Connection failed")
        mock_success = Mock(status_code=200, json=lambda: {"result": "ok"})
        mock_success.headers = {}

        mock_client = Mock()
        mock_client.request.side_effect = [mock_network, mock_success]
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        response = client.get("/test")

        assert response.status_code == 200
        assert mock_client.request.call_count == 2
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_json_parse_error(self, mock_client_class):
        """Should raise error on invalid JSON response."""
        mock_response = Mock(status_code=200)
        mock_response.json.side_effect = ValueError("Invalid JSON")

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")

        with pytest.raises(HttpClientError) as exc_info:
            client.get_json("/test")

        assert "parse JSON" in str(exc_info.value)
        client.close()

    def test_should_retry_logic(self):
        """Should correctly determine which status codes trigger retries."""
        client = BaseHttpClient("https://api.example.com")

        # Should retry: rate limit
        assert client._should_retry(429) is True

        # Should retry: server errors
        assert client._should_retry(500) is True
        assert client._should_retry(502) is True
        assert client._should_retry(503) is True

        # Should retry: timeout
        assert client._should_retry(408) is True

        # Should NOT retry: client errors
        assert client._should_retry(400) is False
        assert client._should_retry(401) is False
        assert client._should_retry(403) is False
        assert client._should_retry(404) is False

        # Should NOT retry: success
        assert client._should_retry(200) is False
        assert client._should_retry(201) is False

        client.close()

    def test_calculate_backoff_increases(self):
        """Backoff delay should increase with attempts."""
        client = BaseHttpClient("https://api.example.com")

        delay_0 = client._calculate_backoff(0)
        delay_1 = client._calculate_backoff(1)
        delay_2 = client._calculate_backoff(2)

        # Each attempt should have longer delay (exponential)
        assert delay_2 > delay_1 > delay_0

        client.close()

    def test_set_rate_limit_delay(self):
        """Should allow updating rate limit delay."""
        client = BaseHttpClient("https://api.example.com")

        client.set_rate_limit_delay(0.5)
        assert client.rate_limit_delay == 0.5

        # Negative values should be clamped to 0
        client.set_rate_limit_delay(-1.0)
        assert client.rate_limit_delay == 0.0

        client.close()

    def test_repr(self):
        """String representation should show base URL."""
        client = BaseHttpClient("https://api.example.com")
        assert "BaseHttpClient" in repr(client)
        assert "https://api.example.com" in repr(client)
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_query_params_passed_correctly(self, mock_client_class):
        """Should pass query parameters correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {}

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        client.get("/test", params={"key": "value", "limit": 10})

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["params"] == {"key": "value", "limit": 10}
        client.close()

    @patch("pmirror.data.client.httpx.Client")
    def test_headers_passed_correctly(self, mock_client_class):
        """Should pass custom headers correctly."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.json.return_value = {}

        mock_client = Mock()
        mock_client.request.return_value = mock_response
        mock_client_class.return_value = mock_client

        client = BaseHttpClient("https://api.example.com")
        client.get("/test", headers={"Authorization": "Bearer token"})

        call_kwargs = mock_client.request.call_args[1]
        assert call_kwargs["headers"] == {"Authorization": "Bearer token"}
        client.close()
