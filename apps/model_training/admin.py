from django.contrib import admin
from .models import ForecastModel, ForecastResult

@admin.register(ForecastModel)
class ForecastModelAdmin(admin.ModelAdmin):
    list_display = ['model_name', 'sales_region_code', 'material_number', 'model_type', 
                   'accuracy', 'mae', 'rmse', 'is_overfit', 'created_at']
    search_fields = ['model_name', 'sales_region_code', 'material_number']
    list_filter = ['model_type', 'is_overfit', 'created_at']
    date_hierarchy = 'created_at'

@admin.register(ForecastResult)
class ForecastResultAdmin(admin.ModelAdmin):
    list_display = ['sales_region_code', 'material_number', 'date', 'forecast_quantity', 
                   'actual_quantity', 'model_used']
    search_fields = ['sales_region_code', 'material_number']
    list_filter = ['model_used', 'date']
    date_hierarchy = 'date'