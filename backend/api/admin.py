from __future__ import annotations

from django.contrib import admin

from api.models import Pipeline, PipelineStep


class PipelineStepInline(admin.TabularInline):
    model = PipelineStep
    extra = 0


@admin.register(Pipeline)
class PipelineAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "user", "created_at")
    list_filter = ("user",)
    search_fields = ("name",)
    readonly_fields = ("created_at",)
    inlines = [PipelineStepInline]


@admin.register(PipelineStep)
class PipelineStepAdmin(admin.ModelAdmin):
    list_display = ("id", "pipeline", "order", "model")
    list_filter = ("model",)
