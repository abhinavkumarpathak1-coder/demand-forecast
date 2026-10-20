from django.urls import path
from . import views

app_name = 'insight'

urlpatterns = [
    path('', views.index, name='index'),
]
