from django.contrib import admin

from api.models import Pipeline, PipelineStep

admin.site.register(Pipeline)
admin.site.register(PipelineStep)
