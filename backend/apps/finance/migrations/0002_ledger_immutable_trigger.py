from django.db import migrations

SQL = """
CREATE OR REPLACE FUNCTION aawen_forbid_change() RETURNS trigger AS $$
BEGIN
  RAISE EXCEPTION 'append-only table %: % is not allowed', TG_TABLE_NAME, TG_OP;
END; $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS ledger_immutable ON finance_ledgerentry;
CREATE TRIGGER ledger_immutable BEFORE UPDATE OR DELETE ON finance_ledgerentry
  FOR EACH ROW EXECUTE FUNCTION aawen_forbid_change();
"""
REVERSE = "DROP TRIGGER IF EXISTS ledger_immutable ON finance_ledgerentry;"


class Migration(migrations.Migration):
    dependencies = [("finance", "0001_initial")]
    operations = [migrations.RunSQL(SQL, REVERSE)]
