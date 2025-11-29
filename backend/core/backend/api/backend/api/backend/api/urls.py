from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import PositionViewSet, CandidateViewSet, VerifyRequestAPIView, VerifyConfirmAPIView, BallotRetrieveAPIView, VoteAPIView

router = DefaultRouter()
router.register(r'positions', PositionViewSet, basename='position')
router.register(r'candidates', CandidateViewSet, basename='candidate')

urlpatterns = [
    path('', include(router.urls)),
    path('verify/request-otp/', VerifyRequestAPIView.as_view(), name='verify-request'),
    path('verify/confirm/', VerifyConfirmAPIView.as_view(), name='verify-confirm'),
    path('ballot/', BallotRetrieveAPIView.as_view(), name='ballot-retrieve'),
    path('vote/', VoteAPIView.as_view(), name='vote'),
]