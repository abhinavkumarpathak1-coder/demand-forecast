from django.urls import path
from . import views

app_name = 'user_management'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('logout/', views.logout_view, name='logout'),
    path('permissions/', views.permissions, name='permissions'),
]
