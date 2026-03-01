from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import protected_view, chat_view, PipelineViewSet, run_pipeline, generate_pipeline, RegisterView
from .n8n_views import list_workflows, get_workflow, list_executions, trigger_webhook, n8n_health

router = DefaultRouter()
router.register(r'pipelines', PipelineViewSet, basename='pipeline')

urlpatterns = [
    path('', include(router.urls)),
    path('register', RegisterView.as_view(), name='auth_register'),
    path('login', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh', TokenRefreshView.as_view(), name='token_refresh'),
    path('protected', protected_view, name='protected_view'),
    path('chat', chat_view, name='chat_view'),
    path('pipelines/<int:pipeline_id>/run', run_pipeline, name='run_pipeline'),
    path('pipelines/generate', generate_pipeline, name='generate_pipeline'),
    # n8n proxy endpoints
    path('n8n/health', n8n_health, name='n8n_health'),
    path('n8n/workflows', list_workflows, name='n8n_list_workflows'),
    path('n8n/workflows/<int:workflow_id>', get_workflow, name='n8n_get_workflow'),
    path('n8n/executions', list_executions, name='n8n_list_executions'),
    path('n8n/webhooks/<path:webhook_path>', trigger_webhook, name='n8n_trigger_webhook'),
]