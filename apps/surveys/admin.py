from __future__ import annotations

from django.contrib import admin

from apps.surveys.models import Field, Section, Survey


class FieldInline(admin.TabularInline):
    model = Field
    extra = 0
    fields = ("position", "key", "type", "label", "required")


class SectionInline(admin.TabularInline):
    model = Section
    extra = 0
    fields = ("position", "title")
    show_change_link = True


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("title", "version", "status", "organization", "created_at")
    list_filter = ("status", "organization")
    search_fields = ("title",)
    readonly_fields = (
        "survey_group_id",
        "version",
        "published_at",
        "created_at",
        "updated_at",
    )
    inlines = [SectionInline]


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ("title", "survey", "position")
    inlines = [FieldInline]


@admin.register(Field)
class FieldAdmin(admin.ModelAdmin):
    list_display = ("key", "type", "section", "position", "required")
    list_filter = ("type", "required")
    search_fields = ("key", "label")
