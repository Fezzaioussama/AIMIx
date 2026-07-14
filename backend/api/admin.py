from django.contrib import admin

from api.models import (
    Pipeline,
    PipelineStep,
    WorkflowChatSession,
    WorkflowChatMessage,
)


class WorkflowChatMessageInline(admin.TabularInline):
    model = WorkflowChatMessage
    extra = 0
    readonly_fields = ("role", "content", "created_at")
    can_delete = False


@admin.register(WorkflowChatSession)
class WorkflowChatSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "state", "iteration_count", "n8n_workflow_id", "updated_at")
    list_filter = ("state",)
    search_fields = ("title", "initial_prompt", "n8n_workflow_id")
    readonly_fields = ("created_at", "updated_at")
    inlines = [WorkflowChatMessageInline]


@admin.register(WorkflowChatMessage)
class WorkflowChatMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "role", "created_at")
    list_filter = ("role",)


admin.site.register(Pipeline)
admin.site.register(PipelineStep)
