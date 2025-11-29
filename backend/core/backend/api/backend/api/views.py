from rest_framework import viewsets, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .serializers import (PositionSerializer, CandidateSerializer, CandidateApproveSerializer,
                          VerifyRequestSerializer, VerifyConfirmSerializer, BallotSerializer, VoteInputSerializer)
from core.models import Position, Candidate, EligibleVoter, Verification, Ballot, Vote, AuditLog
import uuid, hashlib, secrets
from django.conf import settings
from django.core.mail import send_mail

def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()

def _audit(actor_type, actor_id, action, entity, entity_id=None, payload=None):
    AuditLog.objects.create(
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        entity=entity,
        entity_id=str(entity_id) if entity_id else None,
        payload=payload or {}
    )

class PositionViewSet(viewsets.ModelViewSet):
    queryset = Position.objects.all()
    serializer_class = PositionSerializer
    permission_classes = [IsAuthenticated]

class CandidateViewSet(viewsets.ModelViewSet):
    queryset = Candidate.objects.all()
    serializer_class = CandidateSerializer
    permission_classes = [AllowAny]  # allow candidate submissions anonymously if desired

    def perform_create(self, serializer):
        instance = serializer.save()
        _audit("USER", None, "candidate_submitted", "Candidate", instance.id, {"status": instance.status})

    @action(detail=True, methods=['patch'], permission_classes=[IsAuthenticated])
    def decision(self, request, pk=None):
        candidate = get_object_or_404(Candidate, pk=pk)
        serializer = CandidateApproveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = serializer.validated_data['action']
        reason = serializer.validated_data.get('reason', '')
        if action == 'approve':
            candidate.status = Candidate.STATUS_APPROVED
            candidate.reason = ''
        else:
            candidate.status = Candidate.STATUS_REJECTED
            candidate.reason = reason
        candidate.decision_at = timezone.now()
        candidate.decided_by = request.user
        candidate.save()
        _audit("USER", str(request.user.id), f"candidate_{action}", "Candidate", candidate.id, {"reason": reason})
        return Response(CandidateSerializer(candidate).data)

class VerifyRequestAPIView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reg_no = serializer.validated_data['reg_no']
        method = serializer.validated_data['method']
        try:
            voter = EligibleVoter.objects.get(reg_no=reg_no, status=EligibleVoter.STATUS_ELIGIBLE)
        except EligibleVoter.DoesNotExist:
            return Response({"message": "Not eligible"}, status=status.HTTP_400_BAD_REQUEST)

        # generate OTP (in dev use simple numeric)
        otp = str(secrets.randbelow(900000) + 100000)
        otp_hash = hashlib.sha256(otp.encode()).hexdigest()
        verification = Verification.objects.create(voter=voter, method=method, otp_hash=otp_hash)
        # send OTP via email (console backend will output)
        if method == 'email' and voter.email:
            send_mail("Your EVote OTP", f"Your code is {otp}", settings.DEFAULT_FROM_EMAIL, [voter.email])
        # TODO: implement rate-limiting with DRF throttle classes and IP checks
        _audit("SYSTEM", None, "verification_requested", "Verification", verification.id, {"voter": str(voter.id), "method": method})
        # Return challenge id (UUID of verification) to the client
        return Response({"challenge_id": str(verification.id)}, status=status.HTTP_201_CREATED)

class VerifyConfirmAPIView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = VerifyConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        challenge_id = serializer.validated_data['challenge_id']
        code = serializer.validated_data['code']
        verification = get_object_or_404(Verification, pk=challenge_id)
        if verification.verified_at:
            return Response({"message": "Already verified"}, status=status.HTTP_400_BAD_REQUEST)
        if hashlib.sha256(code.encode()).hexdigest() != verification.otp_hash:
            return Response({"message": "Invalid code"}, status=status.HTTP_400_BAD_REQUEST)
        # mark verified and issue single-use ballot token
        verification.verified_at = timezone.now()
        token = str(uuid.uuid4())
        token_hash = _hash_token(token)
        verification.ballot_token_hash = token_hash
        verification.save()
        ballot = Ballot.objects.create(verification=verification, token_hash=token_hash)
        _audit("USER", None, "verification_confirmed", "Verification", verification.id, {"ballot": str(ballot.id)})
        # Return raw token to client (must be used once). Note: in production consider short TTL and secure transport.
        return Response({"ballot_token": token})

class BallotRetrieveAPIView(views.APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        token = request.query_params.get('token') or request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return Response({"message": "Missing token"}, status=status.HTTP_401_UNAUTHORIZED)
        token_hash = _hash_token(token)
        try:
            ballot = Ballot.objects.get(token_hash=token_hash)
        except Ballot.DoesNotExist:
            return Response({"message": "Invalid token"}, status=status.HTTP_401_UNAUTHORIZED)
        if ballot.consumed_at:
            return Response({"message": "Token already used"}, status=status.HTTP_400_BAD_REQUEST)
        # Return positions and candidates for open elections
        positions = Position.objects.filter(opens_at__lte=timezone.now(), closes_at__gte=timezone.now())
        result = []
        for p in positions:
            cands = p.candidates.filter(status=Candidate.STATUS_APPROVED)
            result.append({
                "id": str(p.id),
                "name": p.name,
                "seats": p.seats,
                "candidates": [{"id": str(c.id), "name": c.name, "program": c.program} for c in cands]
            })
        _audit("SYSTEM", None, "ballot_viewed", "Ballot", ballot.id, {"positions_returned": len(result)})
        return Response({"positions": result})

class VoteAPIView(views.APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        # Accept token in Authorization header or body
        token = request.headers.get('Authorization', '').replace('Bearer ', '') or request.data.get('token')
        if not token:
            return Response({"message": "Missing token"}, status=status.HTTP_401_UNAUTHORIZED)
        token_hash = _hash_token(token)
        try:
            ballot = Ballot.objects.get(token_hash=token_hash)
        except Ballot.DoesNotExist:
            return Response({"message": "Invalid token"}, status=status.HTTP_401_UNAUTHORIZED)
        if ballot.consumed_at:
            return Response({"message": "Token already used"}, status=status.HTTP_400_BAD_REQUEST)
        serializer = VoteInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        votes_in = serializer.validated_data['votes']
        # Validate and create votes
        created = []
        for v in votes_in:
            position_id = v.get('position_id')
            candidate_id = v.get('candidate_id')
            # basic validations
            pos = get_object_or_404(Position, pk=position_id)
            if pos.opens_at > timezone.now() or pos.closes_at < timezone.now():
                return Response({"message": "Position not open"}, status=status.HTTP_400_BAD_REQUEST)
            cand = get_object_or_404(Candidate, pk=candidate_id, position=pos, status=Candidate.STATUS_APPROVED)
            # ensure ballot hasn't voted for this position
            if Vote.objects.filter(ballot=ballot, position=pos).exists():
                return Response({"message": "Already voted for position"}, status=status.HTTP_400_BAD_REQUEST)
            vote = Vote.objects.create(ballot=ballot, position=pos, candidate=cand)
            created.append(str(vote.id))
        ballot.consumed_at = timezone.now()
        ballot.save()
        _audit("USER", None, "votes_cast", "Ballot", ballot.id, {"votes": created})
        return Response({"status": "ok", "votes": created}, status=status.HTTP_201_CREATED)