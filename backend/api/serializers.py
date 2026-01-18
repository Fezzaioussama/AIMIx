from rest_framework import serializers
from .models import Pipeline, PipelineStep

class PipelineStepSerializer(serializers.ModelSerializer):
    class Meta:
        model = PipelineStep
        fields = ['id', 'order', 'prompt', 'model']

class PipelineSerializer(serializers.ModelSerializer):
    steps = PipelineStepSerializer(many=True)

    class Meta:
        model = Pipeline
        fields = ['id', 'name', 'user', 'created_at', 'steps']
        read_only_fields = ['user']

    def create(self, validated_data):
        steps_data = validated_data.pop('steps')
        pipeline = Pipeline.objects.create(**validated_data)
        for step_data in steps_data:
            PipelineStep.objects.create(pipeline=pipeline, **step_data)
        return pipeline

    def update(self, instance, validated_data):
        steps_data = validated_data.pop('steps')
        instance.name = validated_data.get('name', instance.name)
        instance.save()

        # Simple approach: clear and recreate steps
        instance.steps.all().delete()
        for step_data in steps_data:
            PipelineStep.objects.create(pipeline=instance, **step_data)
        
        return instance
