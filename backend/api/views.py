from django.contrib.auth import authenticate
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

@api_view(['POST'])
def login_view(request):
    # 1. Get data from Angular
    username = request.data.get('username')
    password = request.data.get('password')

    # 2. Check if user exists in the Database
    user = authenticate(username=username, password=password)

    if user is not None:
        # 3. Success! Return a token (we'll send a simple message for now)
        return Response({
            "message": "Login successful!", 
            "token": "fake-jwt-token-django" 
        }, status=status.HTTP_200_OK)
    else:
        # 4. Failure
        return Response({"message": "Invalid credentials"}, status=status.HTTP_401_UNAUTHORIZED)