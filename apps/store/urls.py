from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("mills", views.FeedMillViewSet, basename="mill")
router.register("products", views.ProductViewSet, basename="product")
router.register("orders", views.CreditOrderViewSet, basename="order")
router.register("stock-movements", views.StockMovementViewSet, basename="stockmovement")
router.register("purchase-orders", views.PurchaseOrderViewSet, basename="purchaseorder")
router.register("stock-takes", views.StockTakeViewSet, basename="stocktake")
router.register("cash-sales", views.CashSaleViewSet, basename="cashsale")

urlpatterns = router.urls
