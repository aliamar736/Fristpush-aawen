#!/usr/bin/env bash
# Runs a CI step; on failure, posts the last lines of its output as an error annotation (readable via the API).
# usage: tool/ci_step.sh "<title>" <command...>
title="$1"; shift
out="$(mktemp)"
"$@" 2>&1 | tee "$out"
rc=${PIPESTATUS[0]}
if [ "$rc" -ne 0 ]; then
  # drop blank lines and download progress bars, keep Gradle's own error block plus the tail
  grep -v -e '^\s*$' -e 'Unzipping' -e '^\[=*' "$out" > "$out.f"
  { grep -n -A30 -e 'What went wrong' -e 'FAILURE:' -e ': error:' -e '^e: ' "$out.f" | head -n 120; echo '--- tail ---'; tail -n 40 "$out.f"; } > "$out.m"
  msg="$(cat "$out.m" | sed -e 's/%/%25/g' -e 's/\r//g' | awk '{printf "%s%%0A", $0}')"
  echo "::error title=${title} failed (exit ${rc})::${msg}"
fi
exit "$rc"
