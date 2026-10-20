from django.contrib import admin
from .models import ForecastScenario

@admin.register(ForecastScenario)
class ForecastScenarioAdmin(admin.ModelAdmin):
    list_display = ['name', 'region', 'sku', 'forecast_period', 
                   'created_by', 'created_at']
    search_fields = ['name', 'region', 'sku', 'created_by']
    list_filter = ['created_at']
    date_hierarchy = 'created_at'