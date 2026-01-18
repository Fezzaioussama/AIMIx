import os
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from server_llm.server_llm import TogetherAIsServerLLM
from server_llm.data_models import LLMTogetherAI
from dotenv import load_dotenv

# Load env at the top level
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

def get_ai_service():
    """ Helper to get or initialize the AI service with the current key. """
    togai_api_key = os.getenv('TOGAI_API_KEY')
    if not togai_api_key or 'your_api_key_here' in togai_api_key:
        return None, "API Key is missing or invalid in .env"
    
    try:
        return TogetherAIsServerLLM(api_key_togai=togai_api_key), None
    except Exception as e:
        return None, str(e)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def protected_view(request):
    """
    A view that requires a valid JWT token to access.
    """
    return Response({
        "message": f"Hello {request.user.username}, you are successfully authenticated with a real JWT!",
        "user_id": request.user.id,
        "email": request.user.email
    })

from django.http import StreamingHttpResponse
import json

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def chat_view(request):
    """
    Protected chat endpoint that interfaces with TogetherAI using Streaming.
    """
    prompt = request.data.get('prompt')
    if not prompt:
        return Response({"error": "Prompt is required"}, status=400)
    
    ai_service, error = get_ai_service()
    if error:
        return Response({
            "error": "AI Service configuration issue.",
            "details": f"{error}. Please check your backend/.env file."
        }, status=503)

    try:
        model = LLMTogetherAI.Llama4_Maverick_17B_128E 
        print(f"Streaming response using model: {model}")

        def stream_generator():
            for chunk in ai_service.generate_streaming_response(prompt=prompt, llm=model):
                yield chunk

        return StreamingHttpResponse(stream_generator(), content_type='text/plain')
    except Exception as e:
        error_msg = str(e)
        print(f"TogetherAI Error: {error_msg}")
        return Response({
            "error": "AI Generation Failed",
            "details": error_msg
        }, status=500)

from rest_framework import viewsets
from .models import Pipeline, PipelineStep
from .serializers import PipelineSerializer

class PipelineViewSet(viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = PipelineSerializer

    def get_queryset(self):
        return Pipeline.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def run_pipeline(request, pipeline_id):
    """
    Executes a multi-step pipeline sequentially.
    """
    try:
        pipeline = Pipeline.objects.get(id=pipeline_id, user=request.user)
    except Pipeline.DoesNotExist:
        return Response({"error": "Pipeline not found"}, status=404)

    initial_input = request.data.get('input', '')
    if not initial_input:
        return Response({"error": "Initial input is required"}, status=400)

    ai_service, error = get_ai_service()
    if error:
        return Response({"error": "AI Service not configured", "details": error}, status=503)

    current_input = initial_input
    results = []

    try:
        for step in pipeline.steps.all():
            print(f"Executing {pipeline.name} - Step {step.order} using {step.model}")
            
            # Prepare prompt by replacing placeholder {input}
            # If no placeholder, append the input
            if "{input}" in step.prompt:
                prompt = step.prompt.format(input=current_input)
            else:
                prompt = f"{step.prompt}\n\nInput: {current_input}"

            response = ai_service.generate_response(prompt=prompt, llm=step.model)
            
            results.append({
                "step_order": step.order,
                "model": step.model,
                "input_used": current_input,
                "output": response
            })
            
            # Result of this step becomes input for next step
            current_input = response

        return Response({
            "pipeline_name": pipeline.name,
            "final_output": current_input,
            "intermediate_results": results
        })

    except Exception as e:
        return Response({"error": f"Pipeline execution failed at step {len(results) + 1}: {str(e)}"}, status=500)