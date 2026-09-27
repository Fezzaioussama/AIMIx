from __future__ import annotations

from rest_framework import serializers


class ChatRequestSerializer(serializers.Serializer):
    """Contract for POST /api/chat."""

    prompt = serializers.CharField(trim_whitespace=True, allow_blank=False)
