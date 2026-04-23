from __future__ import annotations

from django.contrib import admin

from apps.responses.models import Answer, Response


class AnswerInline(admin.TabularInline):
    model = Answer
    extra = 0
    fields = ("field_key", "value_json", "value_encrypted")
    readonly_fields = ("field_key", "value_json", "value_encrypted")
    can_delete = False


@admin.register(Response)
class ResponseAdmin(admin.ModelAdmin):
    list_display = ("id", "survey", "respondent", "status", "submitted_at", "started_at")
    list_filter = ("status", "organization", "survey")
    search_fields = ("respondent__email",)
    readonly_fields = ("started_at", "submitted_at")
    inlines = [AnswerInline]


@admin.register(Answer)
class AnswerAdmin(admin.ModelAdmin):
    list_display = ("response", "field_key", "has_ciphertext", "organization")
    list_filter = ("organization",)
    search_fields = ("field_key",)
    readonly_fields = ("value_json", "value_encrypted")

    @admin.display(boolean=True, description="Encrypted?")
    def has_ciphertext(self, obj: Answer) -> bool:
        return obj.value_encrypted is not None
