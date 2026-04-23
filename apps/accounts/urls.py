from __future__ import annotations

from django.urls import path

from apps.accounts.views import LoginView, LogoutView, TokenView

app_name = "accounts"

urlpatterns = [
    path("login", LoginView.as_view(), name="login"),
    path("token", TokenView.as_view(), name="token"),
    path("logout", LogoutView.as_view(), name="logout"),
]
