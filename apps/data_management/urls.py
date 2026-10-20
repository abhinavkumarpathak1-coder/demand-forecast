from django.urls import path
from . import views

app_name = 'data'

urlpatterns = [
    path('upload/', views.upload_data, name='upload'),
    path('view/', views.view_data, name='view_data'),
    path('export/', views.export_data, name='export_data'),
    path('adjust/', views.adjust_data, name='adjust_data'),
    path('download-sales-template/', views.download_sales_template, name='download_sales_template'),
    path('download-promotion-template/', views.download_promotion_template, name='download_promotion_template'),
]