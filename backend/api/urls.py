from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from api.endpoints.auth import RegisterView, protected_view
from api.endpoints.chat import chat_view
from api.endpoints.n8n import (
    activate_workflow,
    autofix_workflow_endpoint,
    deactivate_workflow,
    generate_workflow,
    get_execution,
    get_workflow,
    list_node_types,
    list_executions,
    list_workflows,
    n8n_health,
    n8n_info,
    retry_execution,
    stop_execution,
    trigger_webhook,
)
from api.endpoints.pipelines import PipelineViewSet, generate_pipeline, run_pipeline

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
    path('n8n/info', n8n_info, name='n8n_info'),
    path('n8n/nodes', list_node_types, name='n8n_list_node_types'),
    path('n8n/workflows', list_workflows, name='n8n_list_workflows'),
    path('n8n/workflows/generate', generate_workflow, name='n8n_generate_workflow'),
    path('n8n/workflows/<str:workflow_id>', get_workflow, name='n8n_get_workflow'),
    path('n8n/workflows/<str:workflow_id>/activate', activate_workflow, name='n8n_activate_workflow'),
    path('n8n/workflows/<str:workflow_id>/deactivate', deactivate_workflow, name='n8n_deactivate_workflow'),
    path('n8n/workflows/<str:workflow_id>/autofix', autofix_workflow_endpoint, name='n8n_autofix_workflow'),
    path('n8n/executions', list_executions, name='n8n_list_executions'),
    path('n8n/executions/<str:execution_id>', get_execution, name='n8n_get_execution'),
    path('n8n/executions/<str:execution_id>/retry', retry_execution, name='n8n_retry_execution'),
    path('n8n/executions/<str:execution_id>/stop', stop_execution, name='n8n_stop_execution'),
    path('n8n/webhooks/<path:webhook_path>', trigger_webhook, name='n8n_trigger_webhook'),
]
