from rest_framework import serializers

from apps.farmers.models import Farmer

from .models import Animal, AnimalMilkRecord, HealthEvent
from .services import summarize


class AnimalSerializer(serializers.ModelSerializer):
    farmer = serializers.PrimaryKeyRelatedField(queryset=Farmer.objects.all(), required=False)
    farmer_name = serializers.CharField(source="farmer.full_name", read_only=True)

    class Meta:
        model = Animal
        fields = "__all__"

    def to_representation(self, a):
        data = super().to_representation(a)
        data.update(summarize(list(a.events.all())))   # events are prefetched by the view
        return data


class HealthEventSerializer(serializers.ModelSerializer):
    animal_tag = serializers.CharField(source="animal.tag", read_only=True)
    farmer_name = serializers.CharField(source="animal.farmer.full_name", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)

    class Meta:
        model = HealthEvent
        fields = "__all__"
        read_only_fields = ["withdrawal_ends", "recorded_by", "expense"]


class AnimalMilkRecordSerializer(serializers.ModelSerializer):
    animal_tag = serializers.CharField(source="animal.tag", read_only=True)

    class Meta:
        model = AnimalMilkRecord
        fields = "__all__"
        read_only_fields = ["recorded_by"]
