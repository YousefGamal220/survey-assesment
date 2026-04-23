from __future__ import annotations

from django.contrib.auth import authenticate, get_user_model
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Membership
from apps.organizations.models import Organization

User = get_user_model()


class MembershipSerializer(serializers.ModelSerializer):
    org_id = serializers.UUIDField(source="organization.id", read_only=True)
    org_name = serializers.CharField(source="organization.name", read_only=True)

    class Meta:
        model = Membership
        fields = ["id", "org_id", "org_name", "role"]


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        email = attrs["email"].lower()
        user = authenticate(username=email, password=attrs["password"])
        if user is None or not user.is_active:
            raise exceptions.AuthenticationFailed("invalid credentials")
        attrs["user"] = user
        return attrs


class LoginResponseSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    memberships = MembershipSerializer(many=True)


class TokenRequestSerializer(serializers.Serializer):
    refresh = serializers.CharField()
    organization_id = serializers.UUIDField()

    def validate(self, attrs):
        try:
            refresh = RefreshToken(attrs["refresh"])
        except Exception as exc:
            raise exceptions.AuthenticationFailed("invalid refresh token") from exc

        user_id = refresh.payload.get("user_id")
        if user_id is None:
            raise exceptions.AuthenticationFailed("invalid refresh token")
        try:
            user = User.objects.get(pk=user_id, is_active=True)
        except User.DoesNotExist as exc:
            raise exceptions.AuthenticationFailed("user not found") from exc

        try:
            org = Organization.objects.get(pk=attrs["organization_id"], is_active=True)
        except Organization.DoesNotExist as exc:
            raise exceptions.PermissionDenied("organization not found or inactive") from exc

        try:
            membership = Membership.objects.get(user=user, organization=org, is_active=True)
        except Membership.DoesNotExist as exc:
            raise exceptions.PermissionDenied(
                "user has no active membership for organization"
            ) from exc

        attrs["user"] = user
        attrs["organization"] = org
        attrs["membership"] = membership
        return attrs


class TokenResponseSerializer(serializers.Serializer):
    access = serializers.CharField()


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()
