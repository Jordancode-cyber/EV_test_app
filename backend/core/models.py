from django.db import models
import uuid
from django.contrib.postgres.fields import JSONField
from django.utils import timezone
from django.conf import settings

class Position(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=200)
    seats = models.PositiveSmallIntegerField(default=1)
    opens_at = models.DateTimeField()
    closes_at = models.DateTimeField()
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['opens_at', 'closes_at']),
        ]
        ordering = ['name']

class Candidate(models.Model):
    STATUS_SUBMITTED = "SUBMITTED"
    STATUS_APPROVED = "APPROVED"
    STATUS_REJECTED = "REJECTED"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Submitted"),
        (STATUS_APPROVED, "Approved"),
        (STATUS_REJECTED, "Rejected"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    position = models.ForeignKey(Position, on_delete=models.CASCADE, related_name='candidates')
    name = models.CharField(max_length=200)
    program = models.CharField(max_length=200, blank=True)
    manifesto = models.FileField(upload_to='manifestos/', null=True, blank=True)
    photo = models.ImageField(upload_to='candidate_photos/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_SUBMITTED)
    reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    decision_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        indexes = [
            models.Index(fields=['position', 'status']),
        ]
        ordering = ['position', 'name']

class EligibleVoter(models.Model):
    STATUS_ELIGIBLE = "ELIGIBLE"
    STATUS_BLOCKED = "BLOCKED"
    STATUS_CHOICES = [
        (STATUS_ELIGIBLE, "Eligible"),
        (STATUS_BLOCKED, "Blocked"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    reg_no = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=200)
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=30, null=True, blank=True)
    program = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ELIGIBLE)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['reg_no']),
            models.Index(fields=['status']),
        ]

class Verification(models.Model):
    METHOD_EMAIL = "email"
    METHOD_SMS = "sms"
    METHOD_INAPP = "inapp"
    METHOD_CHOICES = [
        (METHOD_EMAIL, "Email"),
        (METHOD_SMS, "SMS"),
        (METHOD_INAPP, "In-app"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    voter = models.ForeignKey(EligibleVoter, on_delete=models.CASCADE, related_name='verifications')
    method = models.CharField(max_length=10, choices=METHOD_CHOICES)
    otp_hash = models.CharField(max_length=255)
    issued_at = models.DateTimeField(default=timezone.now)
    verified_at = models.DateTimeField(null=True, blank=True)
    ballot_token_hash = models.CharField(max_length=255, null=True, blank=True)
    consumed_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.CharField(max_length=45, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['voter', 'issued_at']),
            models.Index(fields=['verified_at']),
        ]

class Ballot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    verification = models.ForeignKey(Verification, on_delete=models.SET_NULL, null=True, blank=True, related_name='ballots')
    token_hash = models.CharField(max_length=255, unique=True)
    issued_at = models.DateTimeField(default=timezone.now)
    consumed_at = models.DateTimeField(null=True, blank=True)
    election_id = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['issued_at', 'consumed_at']),
        ]

class Vote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, related_name='votes')
    position = models.ForeignKey(Position, on_delete=models.PROTECT)
    candidate = models.ForeignKey(Candidate, on_delete=models.PROTECT)
    cast_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['position', 'candidate']),
            models.Index(fields=['cast_at']),
        ]
        unique_together = [('ballot', 'position')]

class AuditLog(models.Model):
    ACTOR_TYPE_USER = "USER"
    ACTOR_TYPE_SYSTEM = "SYSTEM"
    ACTOR_TYPE_CHOICES = [
        (ACTOR_TYPE_USER, "User"),
        (ACTOR_TYPE_SYSTEM, "System"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor_type = models.CharField(max_length=20, choices=ACTOR_TYPE_CHOICES)
    actor_id = models.CharField(max_length=200, null=True, blank=True)
    action = models.CharField(max_length=200)
    entity = models.CharField(max_length=200)
    entity_id = models.CharField(max_length=200, null=True, blank=True)
    payload = JSONField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=['action', 'entity', 'created_at']),
        ]