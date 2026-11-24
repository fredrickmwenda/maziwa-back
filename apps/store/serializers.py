from rest_framework import serializers

from apps.farmers.models import Farmer

from .models import (CashSale, CashSaleLine, CreditOrder, FEED_TYPES, FeedMill, Product, ProductPrice, PurchaseOrder,
                     PurchaseOrderLine, StockMovement, StockTake, StockTakeLine)


class FeedMillSerializer(serializers.ModelSerializer):
    class Meta:
        model = FeedMill
        fields = "__all__"
        read_only_fields = ["organization"]


class ProductSerializer(serializers.ModelSerializer):
    mill_name = serializers.CharField(source="mill.name", read_only=True, default="")
    feed_type_label = serializers.CharField(source="get_feed_type_display", read_only=True)
    low_stock = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ["organization", "price_updated", "stock_qty"]   # stock only changes through movements

    def get_low_stock(self, p):
        return p.reorder_level > 0 and p.stock_qty <= p.reorder_level


class ProductPriceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductPrice
        fields = ["id", "price", "note", "effective_from"]


class CreditOrderSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    feed_type_label = serializers.SerializerMethodField()
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    farmer = serializers.PrimaryKeyRelatedField(queryset=Farmer.objects.all(), required=False)

    class Meta:
        model = CreditOrder
        fields = ["id", "farmer", "product", "product_name", "feed_type", "feed_type_label", "mill_name",
                  "quantity", "unit_price", "total_cost", "amount_paid", "balance", "created"]
        read_only_fields = ["feed_type", "mill_name", "unit_price", "total_cost", "amount_paid"]

    def get_feed_type_label(self, o):
        return dict(FEED_TYPES).get(o.feed_type, o.feed_type)


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = ["id", "product", "product_name", "kind", "quantity", "balance_after", "reference", "created"]


class PurchaseOrderLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = PurchaseOrderLine
        fields = ["id", "product", "product_name", "quantity", "unit_cost", "received_qty"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    reference = serializers.CharField(read_only=True)
    mill_name = serializers.CharField(source="mill.name", read_only=True, default="")
    total = serializers.DecimalField(max_digits=14, decimal_places=2, read_only=True)
    lines = PurchaseOrderLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ["id", "reference", "mill", "mill_name", "status", "ordered_on", "expected_on", "received_on", "notes", "total", "lines"]


class StockTakeLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = StockTakeLine
        fields = ["product", "product_name", "expected_qty", "counted_qty", "variance", "variance_value"]


class StockTakeSerializer(serializers.ModelSerializer):
    lines = StockTakeLineSerializer(many=True, read_only=True)
    total_variance_value = serializers.SerializerMethodField()

    class Meta:
        model = StockTake
        fields = ["id", "taken_on", "notes", "created", "lines", "total_variance_value"]

    def get_total_variance_value(self, st):
        return sum((l.variance_value for l in st.lines.all()), 0)


class CashSaleLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = CashSaleLine
        fields = ["product", "product_name", "quantity", "unit_price", "line_total"]


class CashSaleSerializer(serializers.ModelSerializer):
    receipt_no = serializers.CharField(read_only=True)
    lines = CashSaleLineSerializer(many=True, read_only=True)

    class Meta:
        model = CashSale
        fields = ["id", "receipt_no", "customer_name", "farmer", "method", "reference", "total", "created", "lines"]
