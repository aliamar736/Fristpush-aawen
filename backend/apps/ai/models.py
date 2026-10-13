from django.conf import settings
from django.db import models


class AiSuggestion(models.Model):
    """Log of AI-assisted suggestions. AI output is advisory only; humans accept or ignore it."""
    kind = models.CharField(max_length=30)  # category | transcript | sensitive | similar
    provider = models.CharField(max_length=20)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    input_excerpt = models.CharField(max_length=200, blank=True)
    output = models.JSONField(default=dict)
    accepted = models.BooleanField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)
