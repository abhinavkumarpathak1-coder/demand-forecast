from django.urls import path
from . import views

app_name = 'forecast'

urlpatterns = [
    path('', views.demand_forecast, name='forecast'),
    path('results/', views.results_page, name='results_page'),
    path('export/', views.export_forecast, name='export'),
    path('update_adjusted_forecast/', views.update_adjusted_forecast, name='update_adjusted_forecast'),
    path('scenario/<int:scenario_id>/', views.load_scenario, name='load_scenario'),
    path('api/refresh-models/', views.refresh_models, name='refresh_models'),
    path('what-if/', views.what_if_analysis, name='what_if'),
]