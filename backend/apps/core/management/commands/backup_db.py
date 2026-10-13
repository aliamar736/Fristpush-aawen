from django.core.management.base import BaseCommand

from apps.core.backup import create_backup


class Command(BaseCommand):
    help = "Create a database (+ local media) backup with a checksum manifest."

    def add_arguments(self, p):
        p.add_argument("--out", default=None)
        p.add_argument("--no-media", action="store_true")

    def handle(self, *a, **o):
        m = create_backup(o["out"], include_media=not o["no_media"])
        self.stdout.write(self.style.SUCCESS(f"backup manifest: {m}"))
