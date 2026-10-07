#!/usr/bin/env bash
# ===========================================================================
# THE FULL CHECK
# Download pinned copies of the TLA+ tools and the Alloy Analyzer (verified
# by SHA-256), run TLC at the full bound, run every Alloy command, then run
# the model-to-code tests.
#
# Usage:   bash verification/run.sh          (from the repository root)
# Needs:   Java 17+, curl, Python with the repo's requirements installed.
# Time:    about 5 minutes, almost all of it TLC at MaxLog = 8.
# ===========================================================================
set -euo pipefail

# --- DRAMATIS PERSONAE ------------------------------------------------------
# HERE        this script's directory (verification/)
# TOOLS       where the jars are cached (verification/.tools, git-ignored)
# TLA_URL, TLA_SHA        TLA+ tools v1.8.0 and its checksum
# ALLOY_URL, ALLOY_SHA    Alloy 6.2.0 and its checksum
HERE="$(cd "$(dirname "$0")" && pwd)"
TOOLS="$HERE/.tools"
TLA_URL="https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar"
TLA_SHA="7beec0f04818732a62fa193731711a99aa4f11279499b2360a7d156c519ea78d"
ALLOY_URL="https://github.com/AlloyTools/org.alloytools.alloy/releases/download/v6.2.0/org.alloytools.alloy.dist.jar"
ALLOY_SHA="6b8c1cb5bc93bedfc7c61435c4e1ab6e688a242dc702a394628d9a9801edb78d"

# --- Scene 1: fetch a jar once, and refuse it if the checksum differs -------
fetch() {  # fetch <url> <sha256> <file>
  if [ ! -f "$3" ]; then curl -fsSL -o "$3" "$1"; fi
  echo "$2  $3" | sha256sum -c --quiet - || { echo "checksum mismatch: $3" >&2; rm -f "$3"; exit 1; }
}
mkdir -p "$TOOLS"
fetch "$TLA_URL" "$TLA_SHA" "$TOOLS/tla2tools.jar"
fetch "$ALLOY_URL" "$ALLOY_SHA" "$TOOLS/alloy.jar"
export TLA2TOOLS_JAR="$TOOLS/tla2tools.jar" ALLOY_JAR="$TOOLS/alloy.jar"

# --- Scene 2: TLC at the full bound (CommitmentStateMachine.cfg) -------------
echo "== TLC: CommitmentStateMachine (MaxLog = 8)"
( cd "$HERE/tla" && java -XX:+UseParallelGC -jar "$TLA2TOOLS_JAR" -workers auto \
    -config CommitmentStateMachine.cfg -metadir "$TOOLS/tlc-states" \
    CommitmentStateMachine.tla | grep -E "states generated|No error|violated|Error" )

# --- Scene 3: every Alloy command (checks UNSAT, runs SAT) -------------------
echo "== Alloy: closure_and_architecture"
java -jar "$ALLOY_JAR" exec -f -c '*' -o "$TOOLS/alloy-out" \
    "$HERE/alloy/closure_and_architecture.als" 2>&1 | grep -E "^ *[0-9]+\. "

# --- Scene 4: the model-to-code tests, with the checkers enabled -------------
echo "== pytest tests/test_verification.py"
( cd "$HERE/.." && python -m pytest tests/test_verification.py -q )

# EXEUNT
