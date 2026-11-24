from rest_framework import serializers

from .models import MilkCollection, MilkRate, QualityTier
from .services import bonus_rate


class MilkCollectionSerializer(serializers.ModelSerializer):
    farmer_name = serializers.CharField(source="farmer.full_name", read_only=True)
    accepted_litres = serializers.DecimalField(max_digits=7, decimal_places=2, read_only=True)
    bonus_rate = serializers.SerializerMethodField()
    reject_label = serializers.CharField(source="get_reject_reason_display", read_only=True)
    route_name = serializers.CharField(source="route.name", read_only=True, default="")
    centre_name = serializers.CharField(source="centre.name", read_only=True, default="")

    class Meta:
        model = MilkCollection
        fields = "__all__"
        read_only_fields = ["organization", "recorded_by", "trip", "route", "centre"]

    def get_bonus_rate(self, c):
        tiers = self.context.get("tiers")  # loaded once by the view
        return None if tiers is None else bonus_rate(tiers, c.fat_percent, c.protein_percent)

    def validate(self, d):
        litres = d.get("litres", getattr(self.instance, "litres", None))
        rejected = d.get("rejected_litres", getattr(self.instance, "rejected_litres", 0)) or 0
        if d.get("alcohol_passed", True) is False:       # a failed alcohol test rejects the whole delivery
            d["rejected_litres"], d["reject_reason"] = litres, "ALCOHOL"
        elif litres is not None and rejected > litres:
            raise serializers.ValidationError({"rejected_litres": "Cannot be more than the litres delivered."})
        elif rejected > 0 and not d.get("reject_reason"):
            d["reject_reason"] = "OTHER"
        return d


class MilkRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MilkRate
        fields = "__all__"
        read_only_fields = ["organization"]


class QualityTierSerializer(serializers.ModelSerializer):
    class Meta:
        model = QualityTier
        fields = "__all__"
        read_only_fields = ["organization"]
