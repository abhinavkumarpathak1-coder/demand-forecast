from django.db import models

class ProductData(models.Model):
    material_name = models.CharField(max_length=100, verbose_name="物料名称")
    material_number = models.CharField(max_length=50, verbose_name="物料号", unique=True)
    product_category_level1 = models.CharField(max_length=50, verbose_name="产品一级分类")
    product_category_level2 = models.CharField(max_length=50, verbose_name="产品二级分类")
    product_category_level3 = models.CharField(max_length=50, verbose_name="产品三级分类")
    product_category_level4 = models.CharField(max_length=50, verbose_name="产品四级分类", null=True, blank=True)
    product_category_level5 = models.CharField(max_length=50, verbose_name="产品五级分类", null=True, blank=True)

    class Meta:
        verbose_name = "产品数据"
        verbose_name_plural = "产品数据"
        ordering = ['material_number']
        indexes = [
            models.Index(fields=['material_number']),
        ]

    def __str__(self):
        return f"{self.material_number} - {self.material_name}"

class SalesData(models.Model):
    product_data = models.ForeignKey(ProductData, on_delete=models.CASCADE, related_name='sales_data', verbose_name="产品数据")  
    sales_region_name = models.CharField(max_length=100, verbose_name="销售区域名称")
    sales_region_code = models.CharField(max_length=20, verbose_name="销售区域代码")
    date = models.DateField(verbose_name="日期")
    sales_quantity = models.FloatField(verbose_name="销量")
    
    class Meta:
        verbose_name = "销售数据"
        verbose_name_plural = "销售数据"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date', 'sales_region_code', 'product_data']),
        ]

    def __str__(self):
        return f"{self.product_data.material_number} | {self.sales_region_code} | {self.date}"

class PromotionData(models.Model):
    product_data = models.ForeignKey(ProductData, on_delete=models.CASCADE, related_name='promotion_data', verbose_name="产品数据") 
    sales_region_code = models.CharField(max_length=20, verbose_name="销售区域代码")
    sales_region_name = models.CharField(max_length=100, verbose_name="销售区域名称")
    date = models.DateField(verbose_name="日期")
    promotion_strength = models.FloatField(verbose_name="促销力度", null=True, blank=True)
    promotion_start_date = models.DateField(verbose_name="促销开始日期", null=True, blank=True)
    promotion_end_date = models.DateField(verbose_name="促销结束日期", null=True, blank=True)
    
    class Meta:
        verbose_name = "促销数据"
        verbose_name_plural = "促销数据"
        ordering = ['-date']
        indexes = [
            models.Index(fields=['date','sales_region_code','product_data']),
        ]

    def __str__(self):
        return f"{self.product_data.material_number} | {self.sales_region_code} | {self.date}"