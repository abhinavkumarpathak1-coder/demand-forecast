from django.urls import path
from . import views

app_name = 'model'

urlpatterns = [
    path('train/', views.train_model, name='train'),
    path('results/', views.model_results, name='results'),
]