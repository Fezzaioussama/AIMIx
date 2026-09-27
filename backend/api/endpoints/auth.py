"""Authentication endpoints."""

from __future__ import annotations

from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from api.http import authenticated_user
from api.serializers import RegisterSerializer


class RegisterView(generics.CreateAPIView):
    """Public on purpose: this is how an account comes into existence (§6)."""

    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def protected_view(request: Request) -> Response:
    """Cheap way for the client to confirm a token is still valid."""
    user = authenticated_user(request)
    return Response(
        {
            "message": f"Hello {user.username}, your token is valid.",
            "user_id": user.pk,
            "email": user.email,
        }
    )
