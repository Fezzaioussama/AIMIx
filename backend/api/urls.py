from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)
from .views import protected_view, chat_view, PipelineViewSet, run_pipeline

router = DefaultRouter()
router.register(r'pipelines', PipelineViewSet, basename='pipeline')

urlpatterns = [
    path('', include(router.urls)),
    path('login', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh', TokenRefreshView.as_view(), name='token_refresh'),
    path('protected', protected_view, name='protected_view'),
    path('chat', chat_view, name='chat_view'),
    path('pipelines/<int:pipeline_id>/run', run_pipeline, name='run_pipeline'),
]