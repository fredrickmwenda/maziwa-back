from django.contrib import admin

from .models import (CashSale, CreditOrder, FeedMill, Product, ProductPrice, PurchaseOrder, StockMovement, StockTake)

for model in (FeedMill, Product, ProductPrice, CreditOrder, StockMovement, PurchaseOrder, StockTake, CashSale):
    admin.site.register(model)
