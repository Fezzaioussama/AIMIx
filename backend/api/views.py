import os
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from server_llm.server_llm import TogetherAIsServerLLM, OpenRouterServerLLM
from server_llm.data_models import LLMTogetherAI, OpenRouterLLM
from dotenv import load_dotenv

# Load env at the top level
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

def get_ai_service():
    """
    Helper to get or initialize the AI service.
    Reads LLM_PROVIDER from .env to select the backend:
      - 'togetherai'  → TogetherAIsServerLLM  (default)
      - 'openrouter'  → OpenRouterServerLLM
    Also returns the default model for that provider.
    """
    provider = os.getenv('LLM_PROVIDER', 'togetherai').strip().lower()

    if provider == 'openrouter':
        api_key = os.getenv('OPEN_ROUTER_KEY')
        if not api_key or 'your_api_key_here' in api_key:
            return None, None, "OPEN_ROUTER_KEY is missing or invalid in .env"
        try:
            return OpenRouterServerLLM(api_key_openrouter=api_key), OpenRouterLLM.Minimax_M2_5, None
        except Exception as e:
            return None, None, str(e)
    else:  # default: togetherai
        api_key = os.getenv('TOGAI_API_KEY')
        if not api_key or 'your_api_key_here' in api_key:
            return None, None, "TOGAI_API_KEY is missing or invalid in .env"
        try:
            return TogetherAIsServerLLM(api_key_togai=api_key), LLMTogetherAI.Llama4_Maverick_17B_128E, None
        except Exception as e:
            return None, None, str(e)

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
    Protected chat endpoint. Uses LLM_PROVIDER from .env to select the backend
    (togetherai or openrouter) and streams the response.
    """
    prompt = request.data.get('prompt')
    if not prompt:
        return Response({"error": "Prompt is required"}, status=400)
    
    ai_service, default_model, error = get_ai_service()
    if error:
        return Response({
            "error": "AI Service configuration issue.",
            "details": f"{error}. Please check your backend/.env file."
        }, status=503)

    try:
        model = default_model
        provider = os.getenv('LLM_PROVIDER', 'togetherai').strip().lower()
        print(f"Streaming response using model: {model} (provider: {provider})")

        def stream_generator():
            for chunk in ai_service.generate_streaming_response(prompt=prompt, llm=model):
                yield chunk

        return StreamingHttpResponse(stream_generator(), content_type='text/plain')
    except Exception as e:
        error_msg = str(e)
        print(f"LLM Error: {error_msg}")
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

    ai_service, _, error = get_ai_service()
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

AVAILABLE_MODELS = [
    'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8',
    'meta-llama/Llama-3-8b-chat-hf',
    'openai/gpt-oss-120b',
    'Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8'
]

PIPELINE_GENERATION_PROMPT = '''You are an AI pipeline architect. Given a user's description of a workflow, generate a structured multi-step pipeline.

Each step should have:
1. A clear, specific prompt template that uses {input} as a placeholder for the previous step's output
2. A recommended model from this list: meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8, meta-llama/Llama-3-8b-chat-hf, openai/gpt-oss-120b, Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8

Respond ONLY with valid JSON in this exact format (no markdown, no explanation):
{
  "name": "Pipeline Name",
  "steps": [
    {"order": 1, "prompt": "Your prompt with {input}", "model": "model-name"},
    {"order": 2, "prompt": "Next prompt with {input}", "model": "model-name"}
  ]
}

User's workflow description:
'''

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def generate_pipeline(request):
    """
    Uses an LLM to automatically generate a pipeline from a natural language description.
    """
    description = request.data.get('description', '')
    planner_model = request.data.get('planner_model', 'meta-llama/Llama-4-Maverick-17B-128E-Instruct-FP8')
    
    if not description:
        return Response({"error": "Description is required"}, status=400)
    
    if planner_model not in AVAILABLE_MODELS:
        return Response({"error": f"Invalid planner model. Choose from: {AVAILABLE_MODELS}"}, status=400)
    
    ai_service, _, error = get_ai_service()
    if error:
        return Response({"error": "AI Service not configured", "details": error}, status=503)
    
    try:
        full_prompt = PIPELINE_GENERATION_PROMPT + description
        response = ai_service.generate_response(prompt=full_prompt, llm=planner_model)
        
        # Parse the JSON response
        import re
        # Extract JSON from response (in case LLM adds extra text)
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            return Response({
                "error": "Failed to parse pipeline structure from AI response",
                "raw_response": response
            }, status=500)
        
        pipeline_data = json.loads(json_match.group())
        
        # Validate structure
        if 'name' not in pipeline_data or 'steps' not in pipeline_data:
            return Response({
                "error": "Invalid pipeline structure returned by AI",
                "data": pipeline_data
            }, status=500)
        
        # Ensure all models are valid, default to first available if not
        for step in pipeline_data['steps']:
            if step.get('model') not in AVAILABLE_MODELS:
                step['model'] = AVAILABLE_MODELS[0]
        
        return Response({
            "generated_pipeline": pipeline_data,
            "available_models": AVAILABLE_MODELS
        })
        
    except json.JSONDecodeError as e:
        return Response({
            "error": "Failed to parse JSON from AI response",
            "details": str(e),
            "raw_response": response
        }, status=500)
    except Exception as e:
        return Response({"error": f"Pipeline generation failed: {str(e)}"}, status=500)

from rest_framework import generics
from rest_framework.permissions import AllowAny
from .serializers import RegisterSerializer
from django.contrib.auth.models import User

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer