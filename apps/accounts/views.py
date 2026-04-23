from __future__ import annotations

import contextlib

from django_ratelimit.core import is_ratelimited
from drf_spectacular.utils import OpenApiExample, extend_schema
from rest_framework import exceptions, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from apps.accounts.models import Membership
from apps.accounts.serializers import (
    LoginResponseSerializer,
    LoginSerializer,
    LogoutSerializer,
    MembershipSerializer,
    TokenRequestSerializer,
    TokenResponseSerializer,
)


def _throttle(request, group: str, rate: str) -> Response | None:
    """Return a 429 Response if the caller exceeds `rate` on this group, else None.

    We use django-ratelimit's programmatic `is_ratelimited` API rather than the
    decorator because DRF-wrapped views don't play nicely with Django decorators.
    """
    limited = is_ratelimited(
        request=request,
        group=group,
        key="ip",
        rate=rate,
        method="POST",
        increment=True,
    )
    if limited:
        return Response(
            {"detail": "too many attempts, please wait before retrying"},
            status=status.HTTP_429_TOO_MANY_REQUESTS,
        )
    return None


@extend_schema(
    tags=["auth"],
    summary="Step 1 — exchange email+password for a refresh token and membership list.",
    request=LoginSerializer,
    responses={200: LoginResponseSerializer, 401: None, 429: None},
    examples=[
        OpenApiExample(
            "demo login",
            value={"email": "demo@survey.yousefgamal.com", "password": "DemoPass2026!"},
            request_only=True,
        ),
    ],
)
class LoginView(APIView):
    authentication_classes: list = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # Brute-force protection: 10 attempts per IP per minute.
        throttled = _throttle(request, "auth:login", "10/m")
        if throttled:
            return throttled

        ser = LoginSerializer(data=request.data)
        try:
            ser.is_valid(raise_exception=True)
        except exceptions.AuthenticationFailed as exc:
            return Response({"detail": str(exc.detail)}, status=status.HTTP_401_UNAUTHORIZED)
        user = ser.validated_data["user"]

        refresh = RefreshToken.for_user(user)
        memberships_qs = Membership.objects.select_related("organization").filter(
            user=user, is_active=True, organization__is_active=True
        )

        return Response(
            {
                "refresh": str(refresh),
                "memberships": MembershipSerializer(memberships_qs, many=True).data,
            }
        )


@extend_schema(
    tags=["auth"],
    summary="Step 2 — exchange refresh + chosen org for an access token.",
    request=TokenRequestSerializer,
    responses={200: TokenResponseSerializer, 401: None, 403: None, 429: None},
    examples=[
        OpenApiExample(
            "org-scoped token",
            value={
                "refresh": "<paste the refresh returned by /auth/login>",
                "organization_id": "00000000-0000-0000-0000-000000000000",
            },
            request_only=True,
        ),
    ],
)
class TokenView(APIView):
    authentication_classes: list = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        throttled = _throttle(request, "auth:token", "30/m")
        if throttled:
            return throttled
        ser = TokenRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data["user"]
        org = ser.validated_data["organization"]
        membership = ser.validated_data["membership"]

        access = AccessToken.for_user(user)
        access["org_id"] = str(org.id)
        access["role"] = membership.role
        return Response({"access": str(access)})


@extend_schema(
    tags=["auth"],
    summary="Blacklist a refresh token (idempotent — invalid tokens return 204).",
    request=LogoutSerializer,
    responses={204: None},
)
class LogoutView(APIView):
    authentication_classes: list = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        ser = LogoutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        # Logout is idempotent: an invalid/expired refresh token is a no-op.
        with contextlib.suppress(TokenError):
            RefreshToken(ser.validated_data["refresh"]).blacklist()
        return Response(status=status.HTTP_204_NO_CONTENT)
