from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.services.llm import get_ai_service


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat_view(request):
    prompt = request.data.get("prompt")
    if not prompt:
        return Response({"error": "Prompt is required"}, status=400)

    ai_service, default_model, error = get_ai_service()
    if error:
        return Response(
            {
                "error": "AI Service configuration issue.",
                "details": f"{error}. Please check your backend/.env file.",
            },
            status=503,
        )

    try:
        def stream_generator():
            for chunk in ai_service.generate_streaming_response(prompt=prompt, llm=default_model):
                yield chunk

        return StreamingHttpResponse(stream_generator(), content_type="text/plain")
    except Exception as exc:
        return Response({"error": "AI Generation Failed", "details": str(exc)}, status=500)
