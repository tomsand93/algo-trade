"""
Base HTTP client with retry logic and exponential backoff.

Provides a robust foundation for API clients with automatic retries,
rate limit handling, and configurable timeouts.
"""

import logging
import random
import time
from typing import Any, TypeVar

import httpx

from pmirror.config import get_settings

T = TypeVar("T")

logger = logging.getLogger(__name__)


class HttpClientError(Exception):
    """Base exception for HTTP client errors."""

    def __init__(self, message: str, status_code: int | None = None, response: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.response = response


class RateLimitError(HttpClientError):
    """Raised when rate limit is exceeded and retries are exhausted."""

    pass


class ApiClientError(HttpClientError):
    """Raised when the API returns an error response."""

    pass


class BaseHttpClient:
    """
    Base HTTP client with retry logic and exponential backoff.

    Features:
    - Automatic retries with exponential backoff
    - Rate limit detection and handling
    - Configurable timeouts
    - Response logging for debugging

    Usage:
        client = BaseHttpClient(base_url="https://api.example.com")
        data = client.get("/endpoint", params={"key": "value"})
    """

    def __init__(
        self,
        base_url: str,
        *,
        settings: Any | None = None,
        client_name: str = "HTTPClient",
    ):
        """
        Initialize the HTTP client.

        Args:
            base_url: Base URL for all requests
            settings: Optional settings object (uses get_settings() if not provided)
            client_name: Name for logging purposes
        """
        self.base_url = base_url.rstrip("/")
        self.client_name = client_name

        # Load settings
        config = settings if settings is not None else get_settings()
        self.api_config = config.api

        # Configure retry settings
        self.max_retries = self.api_config.max_retries
        self.retry_delay = self.api_config.retry_delay
        self.request_timeout = self.api_config.request_timeout
        self.rate_limit_delay = self.api_config.rate_limit_delay

        # Initialize httpx client
        self._client = httpx.Client(
            timeout=self.request_timeout,
            follow_redirects=True,
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def _should_retry(self, status_code: int) -> bool:
        """
        Determine if a request should be retried based on status code.

        Args:
            status_code: HTTP status code

        Returns:
            True if the request should be retried
        """
        # Retry on rate limits (429)
        if status_code == 429:
            return True

        # Retry on server errors (5xx)
        if 500 <= status_code < 600:
            return True

        # Retry on connection timeouts
        if status_code == 0 or status_code is None:
            return True

        # Retry on 408 Request Timeout
        if status_code == 408:
            return True

        return False

    def _get_retry_after(self, response: httpx.Response) -> float | None:
        """
        Get the Retry-After delay from a response.

        Args:
            response: HTTP response object

        Returns:
            Delay in seconds, or None if not specified
        """
        retry_after = response.headers.get("Retry-After")

        if retry_after is None:
            return None

        try:
            # Retry-After can be a number of seconds
            return float(retry_after)
        except ValueError:
            # Or it can be an HTTP-date - skip parsing for simplicity
            logger.warning(f"Could not parse Retry-After header: {retry_after}")
            return None

    def _calculate_backoff(self, attempt: int, retry_after: float | None = None) -> float:
        """
        Calculate exponential backoff delay with jitter.

        Args:
            attempt: Retry attempt number (0-based)
            retry_after: Optional Retry-After header value

        Returns:
            Delay in seconds
        """
        # Use Retry-After if provided
        if retry_after is not None:
            return retry_after

        # Exponential backoff: base_delay * 2^attempt + jitter
        base_delay = self.retry_delay * (2 ** attempt)

        # Add jitter (±25% of base delay) to prevent thundering herd
        jitter = base_delay * 0.25 * (random.random() * 2 - 1)

        return base_delay + jitter

    def _make_request(
        self,
        method: str,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """
        Make an HTTP request with retry logic.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            params: Query parameters
            json_data: JSON request body
            headers: Additional headers
            **kwargs: Additional arguments passed to httpx

        Returns:
            HTTP response object

        Raises:
            HttpClientError: On unrecoverable errors
            RateLimitError: When rate limit is exceeded
            ApiClientError: On API error responses
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        last_error = None

        for attempt in range(self.max_retries + 1):
            try:
                # Add rate limit delay between attempts (after first attempt)
                if attempt > 0:
                    time.sleep(self.rate_limit_delay)

                logger.debug(
                    f"{self.client_name}: {method} {url} (attempt {attempt + 1}/{self.max_retries + 1})"
                )

                response = self._client.request(
                    method=method,
                    url=url,
                    params=params,
                    json=json_data,
                    headers=headers,
                    **kwargs,
                )

                # Check if we should retry
                if self._should_retry(response.status_code):
                    retry_after = self._get_retry_after(response)

                    if attempt < self.max_retries:
                        delay = self._calculate_backoff(attempt, retry_after)
                        logger.warning(
                            f"{self.client_name}: Got status {response.status_code}, "
                            f"retrying in {delay:.2f}s..."
                        )
                        time.sleep(delay)
                        continue
                    else:
                        # Max retries exceeded
                        if response.status_code == 429:
                            raise RateLimitError(
                                f"Rate limit exceeded after {self.max_retries} retries",
                                status_code=response.status_code,
                                response=response,
                            )
                        raise HttpClientError(
                            f"Request failed after {self.max_retries} retries: {response.status_code}",
                            status_code=response.status_code,
                            response=response,
                        )

                # Check for client errors (4xx except 429 which is handled above)
                if 400 <= response.status_code < 500:
                    raise ApiClientError(
                        f"API error: {response.status_code}",
                        status_code=response.status_code,
                        response=response,
                    )

                # Success
                return response

            except httpx.TimeoutException as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(f"{self.client_name}: Timeout, retrying in {delay:.2f}s...")
                    time.sleep(delay)
                    continue
                raise HttpClientError(f"Request timed out after {self.max_retries} retries") from e

            except httpx.NetworkError as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self._calculate_backoff(attempt)
                    logger.warning(
                        f"{self.client_name}: Network error ({type(e).__name__}), "
                        f"retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                    continue
                raise HttpClientError(f"Network error after {self.max_retries} retries: {e}") from e

        # Should not reach here, but just in case
        raise HttpClientError(f"Request failed: {last_error}")

    def get(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a GET request."""
        return self._make_request("GET", endpoint, params=params, headers=headers)

    def post(
        self,
        endpoint: str,
        *,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make a POST request."""
        return self._make_request(
            "POST", endpoint, params=params, json_data=json_data, headers=headers
        )

    def get_json(
        self,
        endpoint: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """
        Make a GET request and parse JSON response.

        Args:
            endpoint: API endpoint path
            params: Query parameters
            headers: Additional headers

        Returns:
            Parsed JSON response
        """
        response = self.get(endpoint, params=params, headers=headers)
        return self._parse_json(response)

    def post_json(
        self,
        endpoint: str,
        *,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        """
        Make a POST request and parse JSON response.

        Args:
            endpoint: API endpoint path
            json_data: JSON request body
            params: Query parameters
            headers: Additional headers

        Returns:
            Parsed JSON response
        """
        response = self.post(endpoint, json_data=json_data, params=params, headers=headers)
        return self._parse_json(response)

    def _parse_json(self, response: httpx.Response) -> Any:
        """
        Parse JSON response with error handling.

        Args:
            response: HTTP response object

        Returns:
            Parsed JSON data

        Raises:
            HttpClientError: If JSON parsing fails
        """
        try:
            return response.json()
        except ValueError as e:
            raise HttpClientError(
                f"Failed to parse JSON response: {e}",
                status_code=response.status_code,
            ) from e

    def set_rate_limit_delay(self, delay: float) -> None:
        """
        Update the rate limit delay between requests.

        Args:
            delay: Delay in seconds
        """
        self.rate_limit_delay = max(0.0, delay)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(base_url='{self.base_url}')"
