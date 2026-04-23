from __future__ import annotations

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient


@pytest.mark.django_db
class TestLoginThrottling:
    def setup_method(self):
        cache.clear()

    def test_login_rate_limit_returns_429(self):
        """10 attempts per minute per IP, then 429s."""
        client = APIClient()
        # 11th attempt should 429
        for i in range(10):
            res = client.post(
                "/api/v1/auth/login",
                {"email": "nope@x.com", "password": "wrong"},
                format="json",
            )
            assert res.status_code in (400, 401), f"attempt {i}: {res.status_code}"

        res = client.post(
            "/api/v1/auth/login",
            {"email": "nope@x.com", "password": "wrong"},
            format="json",
        )
        assert res.status_code == 429
        assert "too many attempts" in res.json()["detail"].lower()
