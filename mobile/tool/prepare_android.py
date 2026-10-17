"""Run after `flutter create`: app name, permissions, and (for demo builds) plain-HTTP access to the server.
usage: python3 tool/prepare_android.py [--allow-http]"""
import re
import sys
from pathlib import Path

manifest = Path(__file__).resolve().parent.parent / "android/app/src/main/AndroidManifest.xml"
xml = manifest.read_text()

PERMS = ["INTERNET", "ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION", "CAMERA", "RECORD_AUDIO"]  # no background location
for p in PERMS:
    tag = f'<uses-permission android:name="android.permission.{p}"/>'
    if tag not in xml:
        xml = xml.replace("<application", f"{tag}\n    <application", 1)

xml = re.sub(r'android:label="[^"]*"', 'android:label="عاون"', xml, count=1)
if "--allow-http" in sys.argv and "usesCleartextTraffic" not in xml:
    # Demo servers without a domain are reached over plain HTTP; production builds use HTTPS only.
    xml = xml.replace("<application", '<application android:usesCleartextTraffic="true"', 1)

manifest.write_text(xml)
print(manifest.read_text())
