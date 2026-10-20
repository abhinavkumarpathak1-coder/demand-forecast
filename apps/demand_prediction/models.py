from django.db import models

class ForecastScenario(models.Model):
    """预测场景"""
    name = models.CharField(max_length=100, verbose_name="场景名称")
    description = models.TextField(verbose_name="场景描述", blank=True)
    created_by = models.CharField(max_length=100, verbose_name="创建人")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    region = models.CharField(max_length=200, verbose_name="销售区域代码")
    sku = models.CharField(max_length=500, verbose_name="物料号/分类代码")
    forecast_period = models.IntegerField(default=12, verbose_name="预测周期(月)")
    hierarchy_level = models.CharField(max_length=20, default='sku', verbose_name="产品层级")
    promotion_type = models.CharField(default='none', max_length=20, verbose_name="促销类型")
    promotion_value = models.FloatField(blank=True, null=True, verbose_name="促销值")

    class Meta:
        verbose_name = "预测场景"
        verbose_name_plural = "预测场景"
        ordering = ['-created_at']