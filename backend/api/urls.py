from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from api.endpoints.auth import RegisterView, protected_view
from api.endpoints.chat import chat_view
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
]
