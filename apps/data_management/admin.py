from django.contrib import admin
from .models import SalesData, PromotionData, ProductData


@admin.register(ProductData)
class ProductDataAdmin(admin.ModelAdmin):
    list_display = ['material_number', 'material_name', 'product_category_level1', 'product_category_level2']
    search_fields = ['material_number', 'material_name']


@admin.register(SalesData)
class SalesDataAdmin(admin.ModelAdmin):
    list_display = ['product_data', 'sales_region_code', 'sales_region_name', 'date', 'sales_quantity']
    search_fields = ['product_data__material_number', 'sales_region_code']
    list_filter = ['sales_region_code', 'date']
    date_hierarchy = 'date'


@admin.register(PromotionData)
class PromotionDataAdmin(admin.ModelAdmin):
    list_display = ['product_data', 'sales_region_code', 'sales_region_name', 'date', 'promotion_strength']
    search_fields = ['product_data__material_number', 'sales_region_code']
    list_filter = ['sales_region_code', 'date']
    date_hierarchy = 'date'