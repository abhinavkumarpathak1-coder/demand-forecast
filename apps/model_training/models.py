from django.db import models

HIERARCHY_CHOICES = [
    ('sku', 'SKU级别'),
    ('category_l1', '一级分类'),
    ('category_l2', '二级分类'),
    ('category_l3', '三级分类'),
    ('category_l4', '四级分类'),
    ('category_l5', '五级分类'),
]

class ForecastModel(models.Model):
    sales_region_code = models.CharField(max_length=20, verbose_name="销售区域代码")
    material_number = models.CharField(max_length=50, verbose_name="物料号/分类代码")
    model_name = models.CharField(max_length=100, verbose_name="模型名称")
    model_type = models.CharField(max_length=50, default="Holt-Winters", verbose_name="模型类型")
    hierarchy_level = models.CharField(max_length=20, default='sku', choices=HIERARCHY_CHOICES, verbose_name="产品层级")
    category_code = models.CharField(max_length=50, null=True, blank=True, verbose_name="分类编码")
    display_name = models.CharField(max_length=200, null=True, blank=True, verbose_name="显示名称")
    training_start_date = models.DateField(verbose_name="训练开始日期")
    training_end_date = models.DateField(verbose_name="训练结束日期")
    accuracy = models.FloatField(verbose_name="准确率", default=0.0)
    mae = models.FloatField(verbose_name="平均绝对误差", default=0.0)
    rmse = models.FloatField(verbose_name="均方根误差", default=0.0)
    is_overfit = models.BooleanField(verbose_name="是否过拟合", default=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    
    class Meta:
        verbose_name = "预测模型"
        verbose_name_plural = "预测模型"
        ordering = ['-created_at']
        unique_together = ['sales_region_code', 'material_number', 'model_type', 'hierarchy_level', 'category_code']

class ForecastResult(models.Model):
    sales_region_code = models.CharField(max_length=20, verbose_name="销售区域代码")
    material_number = models.CharField(max_length=50, verbose_name="物料号/分类代码")
    hierarchy_level = models.CharField(max_length=20, default='sku', choices=HIERARCHY_CHOICES, verbose_name="产品层级")
    category_code = models.CharField(max_length=50, null=True, blank=True, verbose_name="分类编码")
    material_name = models.CharField(max_length=100, null=True, blank=True, verbose_name="物料名称")
    category_l1 = models.CharField(max_length=50, null=True, blank=True, verbose_name="一级分类")
    category_l2 = models.CharField(max_length=50, null=True, blank=True, verbose_name="二级分类")
    category_l3 = models.CharField(max_length=50, null=True, blank=True, verbose_name="三级分类")
    category_l4 = models.CharField(max_length=50, null=True, blank=True, verbose_name="四级分类")
    category_l5 = models.CharField(max_length=50, null=True, blank=True, verbose_name="五级分类")
    date = models.DateField(verbose_name="预测日期")
    actual_quantity = models.FloatField(verbose_name="实际销量", null=True, blank=True)
    forecast_quantity = models.FloatField(verbose_name="预测销量")
    adjusted_forecast_quantity = models.FloatField(verbose_name="调整后预测销量", null=True, blank=True)
    promotion_strength = models.FloatField(verbose_name="促销力度", null=True, blank=True)
    model_used = models.CharField(max_length=50, verbose_name="使用模型", default="Holt-Winters")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    
    class Meta:
        verbose_name = "预测结果"
        verbose_name_plural = "预测结果"
        ordering = ['date']
        indexes = [
            models.Index(fields=['sales_region_code', 'material_number', 'date']),
        ]