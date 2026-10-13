import json

from django.core.management.base import BaseCommand, CommandError

from apps.core.backup import restore_backup


class Command(BaseCommand):
    help = "Restore a backup into a target database and verify row counts against the manifest."

    def add_arguments(self, p):
        p.add_argument("manifest")
        p.add_argument("--target-db", required=True)
        p.add_argument("--drop-existing", action="store_true")

    def handle(self, *a, **o):
        try:
            out = restore_backup(o["manifest"], o["target_db"], o["drop_existing"])
        except RuntimeError as exc:
            raise CommandError(str(exc))
        self.stdout.write(json.dumps(out, ensure_ascii=False, indent=2))
        if not out["ok"]:
            raise CommandError("restore verification failed")
        self.stdout.write(self.style.SUCCESS("restore verified"))
