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
