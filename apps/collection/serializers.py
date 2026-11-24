from decimal import Decimal

from rest_framework import serializers

from .models import CollectionCentre, Route, RouteTrip, Transporter, TransporterPayment

ZERO = Decimal("0")


class CentreSerializer(serializers.ModelSerializer):
    routes = serializers.SerializerMethodField()

    class Meta:
        model = CollectionCentre
        fields = "__all__"
        read_only_fields = ["organization"]

    def get_routes(self, c):
        return c.routes.count()


class TransporterSerializer(serializers.ModelSerializer):
    class Meta:
        model = Transporter
        fields = "__all__"
        read_only_fields = ["organization"]


class RouteSerializer(serializers.ModelSerializer):
    centre_name = serializers.CharField(source="centre.name", read_only=True, default="")
    transporter_name = serializers.CharField(source="transporter.name", read_only=True, default="")
    farmers = serializers.SerializerMethodField()

    class Meta:
        model = Route
        fields = "__all__"
        read_only_fields = ["organization"]

    def get_farmers(self, r):
        return getattr(r, "n_farmers", None) if hasattr(r, "n_farmers") else r.farmers.count()


class RouteTripSerializer(serializers.ModelSerializer):
    route_name = serializers.CharField(source="route.name", read_only=True)
    centre_name = serializers.CharField(source="route.centre.name", read_only=True, default="")
    transporter_name = serializers.CharField(source="transporter.name", read_only=True, default="")
    session_label = serializers.CharField(source="get_session_display", read_only=True)
    delivered = serializers.SerializerMethodField()
    rejected = serializers.SerializerMethodField()
    accepted = serializers.SerializerMethodField()
    farmers = serializers.SerializerMethodField()
    difference = serializers.SerializerMethodField()
    difference_pct = serializers.SerializerMethodField()

    class Meta:
        model = RouteTrip
        fields = ["id", "route", "route_name", "centre_name", "transporter", "transporter_name", "vehicle_reg", "date",
                  "session", "session_label", "status", "delivered", "rejected", "accepted", "farmers", "received_litres",
                  "difference", "difference_pct", "temperature", "received_at", "notes"]

    # totals come from annotations added by the view
    def get_delivered(self, t): return getattr(t, "delivered", None) or ZERO
    def get_rejected(self, t): return getattr(t, "rejected", None) or ZERO
    def get_accepted(self, t): return self.get_delivered(t) - self.get_rejected(t)
    def get_farmers(self, t): return getattr(t, "farmers_n", 0)

    def get_difference(self, t):
        """Litres received at the centre minus litres collected (negative = lost on the way)."""
        return None if t.received_litres is None else t.received_litres - self.get_accepted(t)

    def get_difference_pct(self, t):
        d, acc = self.get_difference(t), self.get_accepted(t)
        return None if d is None or not acc else (d / acc * 100).quantize(Decimal("0.1"))


class TransporterPaymentSerializer(serializers.ModelSerializer):
    transporter_name = serializers.CharField(source="transporter.name", read_only=True)

    class Meta:
        model = TransporterPayment
        fields = ["id", "transporter", "transporter_name", "period_start", "period_end", "litres", "rate", "amount", "reference", "created"]
