from django.contrib.postgres.operations import TrigramExtension
from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION aawen_forbid_change() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'append-only table %: % is not allowed', TG_TABLE_NAME, TG_OP;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_immutable ON core_auditlog;
CREATE TRIGGER audit_immutable BEFORE UPDATE OR DELETE ON core_auditlog
  FOR EACH ROW EXECUTE FUNCTION aawen_forbid_change();
"""


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [TrigramExtension(), migrations.RunSQL(SQL, "DROP TRIGGER IF EXISTS audit_immutable ON core_auditlog;")]
