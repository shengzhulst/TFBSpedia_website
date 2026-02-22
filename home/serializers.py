# home/serializers.py
from rest_framework import serializers

class TFBSSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    seqnames = serializers.CharField(read_only=True)
    start = serializers.IntegerField(read_only=True)
    end = serializers.IntegerField(read_only=True)
    actions = serializers.CharField(read_only=True, required=False)