from django.apps import AppConfig


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        # Register the drf-spectacular extension for TenantAuthentication so
        # OpenAPI declares Bearer-JWT and Swagger renders the Authorize button.
        from apps.accounts import schema  # noqa: F401
