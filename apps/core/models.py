from django.db import models

class SystemLog(models.Model):
    action = models.CharField(max_length=100, verbose_name="操作")
    user = models.CharField(max_length=100, verbose_name="用户")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="时间")
    details = models.TextField(blank=True, verbose_name="详情")
    
    class Meta:
        verbose_name = "系统日志"
        verbose_name_plural = "系统日志"
        ordering = ['-timestamp']