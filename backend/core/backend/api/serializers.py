from rest_framework import serializers
from core.models import Position, Candidate, EligibleVoter, Verification, Ballot, Vote

class PositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Position
        fields = ['id', 'name', 'seats', 'opens_at', 'closes_at']

class CandidateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Candidate
        fields = ['id', 'position', 'name', 'program', 'manifesto', 'photo', 'status', 'reason', 'created_at']

class CandidateApproveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=['approve', 'reject'])
    reason = serializers.CharField(required=False, allow_blank=True)

class VerifyRequestSerializer(serializers.Serializer):
    reg_no = serializers.CharField()
    method = serializers.ChoiceField(choices=['email', 'inapp'])

class VerifyConfirmSerializer(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    code = serializers.CharField()

class BallotSerializer(serializers.ModelSerializer):
    class Meta:
        model = Ballot
        fields = ['id', 'issued_at', 'consumed_at']

class VoteInputSerializer(serializers.Serializer):
    votes = serializers.ListField(
        child=serializers.DictField(child=serializers.CharField()),
        allow_empty=False
    )