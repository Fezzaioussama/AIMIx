from django.contrib.auth.models import User
from rest_framework import generics
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from api.serializers import RegisterSerializer


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def protected_view(request):
    return Response(
        {
            "message": f"Hello {request.user.username}, you are successfully authenticated with a real JWT!",
            "user_id": request.user.id,
            "email": request.user.email,
        }
    )


class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer
