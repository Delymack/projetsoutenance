# backend/apps/accounts/urls.py
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import (
    LoginSendCodeView,
    LoginVerifyView,
    MeView,
    ResendCodeView,
    SignupSendCodeView,
    SignupVerifyView,
)
from .views_api import (
    ForgotPasswordView,
    MagicLinkRequestView,
    RegisterVerifyView,
    RegisterView,
    ResetPasswordView,
    WineTokenObtainPairView,
)
from .views_google import GoogleAuthView

urlpatterns = [
    # --- Flow classique JWT / OTP / Google ---
    path('login/', WineTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('me/', MeView.as_view(), name='auth_me'),
    path('google/', GoogleAuthView.as_view(), name='auth_google'),
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('register/verify/', RegisterVerifyView.as_view(), name='auth_register_verify'),
    path('forgot/', ForgotPasswordView.as_view(), name='auth_forgot'),
    path('reset/', ResetPasswordView.as_view(), name='auth_reset'),
    path('magic-link/', MagicLinkRequestView.as_view(), name='auth_magic_link'),
    # --- Flow par code e-mail / SMS (6 chiffres) ---
    path('signup/send-code/', SignupSendCodeView.as_view(), name='signup-send-code'),
    path('signup/verify/', SignupVerifyView.as_view(), name='signup-verify'),
    path('login/send-code/', LoginSendCodeView.as_view(), name='login-send-code'),
    path('login/verify/', LoginVerifyView.as_view(), name='login-verify'),
    path('resend-code/', ResendCodeView.as_view(), name='resend-code'),
]