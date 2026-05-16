from django.db import models
from django.contrib.auth.models import User

class Pipeline(models.Model):
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

class PipelineStep(models.Model):
    pipeline = models.ForeignKey(Pipeline, related_name='steps', on_delete=models.CASCADE)
    order = models.PositiveIntegerField()
    prompt = models.TextField(help_text="The prompt template for this step. Use {input} as placeholder.")
    model = models.CharField(max_length=100)

    class Meta:
        ordering = ['order']

    def __str__(self):
        return f"{self.pipeline.name} - Step {self.order} ({self.model})"


class WorkflowChatSession(models.Model):
    STATE_DRAFT = "draft"
    STATE_NEEDS_INFO = "needs_info"
    STATE_EXECUTED = "executed"
    STATE_FIXED = "fixed"
    STATE_DONE = "done"
    STATE_FAILED = "failed"
    STATE_CHOICES = [
        (STATE_DRAFT, "Draft"),
        (STATE_NEEDS_INFO, "Needs info"),
        (STATE_EXECUTED, "Executed"),
        (STATE_FIXED, "Fixed"),
        (STATE_DONE, "Done"),
        (STATE_FAILED, "Failed"),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="workflow_chat_sessions")
    title = models.CharField(max_length=120, blank=True)
    initial_prompt = models.TextField()
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_DRAFT)
    n8n_workflow_id = models.CharField(max_length=64, blank=True)
    last_execution_id = models.CharField(max_length=64, blank=True)
    last_plan = models.JSONField(default=dict, blank=True)
    pending_questions = models.JSONField(default=list, blank=True)
    iteration_count = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title or f"Workflow chat {self.pk}"


class WorkflowChatMessage(models.Model):
    ROLE_USER = "user"
    ROLE_ASSISTANT = "assistant"
    ROLE_SYSTEM = "system"
    ROLE_EXECUTION = "execution"
    ROLE_CHOICES = [
        (ROLE_USER, "User"),
        (ROLE_ASSISTANT, "Assistant"),
        (ROLE_SYSTEM, "System"),
        (ROLE_EXECUTION, "Execution"),
    ]

    session = models.ForeignKey(
        WorkflowChatSession,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    content = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self):
        return f"{self.session_id}:{self.role}@{self.created_at:%H:%M:%S}"
