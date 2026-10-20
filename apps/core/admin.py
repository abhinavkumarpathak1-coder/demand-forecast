from django.contrib import admin
from .models import SystemLog

@admin.register(SystemLog)
class SystemLogAdmin(admin.ModelAdmin):
    list_display = ['action', 'user', 'timestamp']
    search_fields = ['action', 'user']
    list_filter = ['timestamp']