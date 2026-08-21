"""
Step 6b Capstone (Gemini twin) -- GOVERNANCE & AUDITABILITY. (module 6.7)

Same four mechanisms, same order, as ../Samples/step6b_governance.py -- and
notice how little of this file is vendor-specific. Redaction, the
hash-chained audit log, the human approval gate, and the retention policy are
ordinary backend engineering discipline; only the RESIDENCY note and the
model call itself (via this folder's step3_agent.py) touch Gemini at all.

  1. REDACT      personal data never reaches the model in the first place
  2. AUDIT       an append-only, tamper-evident record of what happened
  3. APPROVE     the agent may propose a write; a human commits it
  4. RETAIN      what is stored, for how long, and what is never stored

Run:   uv run step6b_governance.py --offline      # no API key, no cost
       uv run step6b_governance.py                # the full path
Deps:  google-genai pydantic
Env:   GEMINI_API_KEY (not needed with --offline)
"""
import argparse
import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from pathlib import Path

AUDIT_LOG = Path("audit-log.jsonl")

# ---------------------------------------------------------------------------
# 1. REDACTION -- keep personal data out of the model call entirely
# ---------------------------------------------------------------------------
# ILLUSTRATIVE patterns, same caveat as the Claude version: real deployments
# use a dedicated PII detection service, because a redactor that quietly
# misses things is worse than none -- it manufactures false confidence.
PATTERNS = {
    "NRIC":  re.compile(r"\b[STFGM]\d{7}[A-Z]\b"),          # Singapore NRIC/FIN
    "EMAIL": re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]+\b"),
    "PHONE": re.compile(r"\b(?:\+65[ -]?)?[89]\d{7}\b"),    # SG mobile
    "CARD":  re.compile(r"\b(?:\d[ -]?){13,19}\b"),
}


def redact(text: str) -> tuple[str, dict[str, str]]:
    """Replace personal data with stable placeholders. The mapping NEVER
    leaves your process -- that is the whole design."""
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}

    def swap(kind: str):
        def _sub(match: re.Match) -> str:
            original = match.group(0)
            for token, value in mapping.items():
                if value == original:
                    return token
            counters[kind] = counters.get(kind, 0) + 1
            token = f"[{kind}_{counters[kind]}]"
            mapping[token] = original
            return token
        return _sub

    safe = text
    for kind, pattern in PATTERNS.items():
        safe = pattern.sub(swap(kind), safe)
    return safe, mapping


def restore(text: str, mapping: dict[str, str]) -> str:
    """Put the real values back, for the human's eyes only."""
    for token, value in mapping.items():
        text = text.replace(token, value)
    return text


# ---------------------------------------------------------------------------
# 2. AUDIT TRAIL -- append-only and tamper-evident
# ---------------------------------------------------------------------------
class AuditLog:
    """A hash-chained JSONL audit log -- identical mechanics to the Claude
    version, because none of this is AI-specific, let alone vendor-specific.
    """

    def __init__(self, path: Path = AUDIT_LOG):
        self.path = path

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        last = None
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = line
        if last is None:
            return "0" * 64
        return json.loads(last)["entry_hash"]

    @staticmethod
    def _hash(prev: str, entry: dict) -> str:
        payload = prev + json.dumps(entry, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def append(self, **fields) -> dict:
        prev = self._last_hash()
        entry = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "prev_hash": prev,
            **fields,
        }
        entry["entry_hash"] = self._hash(prev, entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, sort_keys=True) + "\n")
        return entry

    def verify(self) -> tuple[bool, str]:
        """Recompute the whole chain. This is the report you hand an auditor."""
        if not self.path.exists():
            return True, "no log yet"
        prev = "0" * 64
        count = 0
        with self.path.open(encoding="utf-8") as fh:
            for lineno, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                entry = json.loads(line)
                claimed = entry.pop("entry_hash")
                if entry["prev_hash"] != prev:
                    return False, f"line {lineno}: chain break (prev_hash mismatch)"
                if self._hash(prev, entry) != claimed:
                    return False, f"line {lineno}: entry was modified after writing"
                prev, count = claimed, count + 1
        return True, f"{count} entries verified, chain intact"


def digest(text: str) -> str:
    """Short content hash -- proves what was said without storing it."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# 3. APPROVAL GATE -- the agent proposes, a human commits
# ---------------------------------------------------------------------------
READ_TOOLS = {"search", "calculator"}
WRITE_TOOLS = {"update_resident_count", "send_notice"}

_PENDING: dict[str, dict] = {}


def propose_write(tool: str, args: dict, requested_by: str, audit: AuditLog) -> str:
    """Queue a write instead of performing it."""
    token = str(uuid.uuid4())[:8]
    _PENDING[token] = {"tool": tool, "args": args, "requested_by": requested_by}
    audit.append(event="write_proposed", actor=requested_by,
                 tool=tool, args_hash=digest(json.dumps(args, sort_keys=True)),
                 approval_token=token)
    return (f"PENDING APPROVAL (token {token}): {tool}({args}). "
            "A human must approve this before it takes effect.")


def approve_write(token: str, approver: str, audit: AuditLog) -> str:
    pending = _PENDING.pop(token, None)
    if pending is None:
        audit.append(event="approval_rejected", actor=approver,
                     approval_token=token, reason="unknown or already-used token")
        return f"no pending action with token {token}"
    audit.append(event="write_approved", actor=approver,
                 tool=pending["tool"], approval_token=token,
                 requested_by=pending["requested_by"])
    return f"applied {pending['tool']}({pending['args']}) approved by {approver}"


# ---------------------------------------------------------------------------
# 4. RETENTION & RESIDENCY -- the policy, written down
# ---------------------------------------------------------------------------
POLICY = """
RETENTION
  audit-log.jsonl      kept 7 years    hashes + metadata only, no personal data
  redaction mapping    kept 0 seconds  in-process only, never written to disk
  raw prompts          not stored      redacted text may be sampled for evals
  model responses      not stored      only a content hash is retained

RESIDENCY
  The google-genai SDK can reach Gemini through two backends: the direct
  Gemini Developer API (what config.py uses by default), or Vertex AI, which
  runs inference inside a GCP project and REGION you choose --
  genai.Client(vertexai=True, project=..., location=...). "Which region did
  this inference run in?" is a question you should be able to answer from
  configuration, the same way ../Samples/config.py's Bedrock/Vertex/Foundry
  knob answers it for Claude.

WHAT AN AUDITOR WILL ACTUALLY ASK
  1. What personal data leaves your boundary?        -> redact(), demonstrably
  2. Who asked what, and when?                       -> the audit chain
  3. Could those logs have been altered?             -> verify()
  4. What can the agent change on its own?           -> READ_TOOLS only
  5. How long do you keep any of it?                 -> the table above
"""


# ---------------------------------------------------------------------------
# the demo
# ---------------------------------------------------------------------------
DIRTY_QUESTION = (
    "Resident S1234567D (tan.wei.ming@example.com, mobile 91234567) asked how "
    "many residents live in Dorm A and Dorm B in total. Please also update the "
    "resident count for Dorm A to 481."
)


async def main(offline: bool) -> None:
    audit = AuditLog()
    actor = "officer:wong"

    print("=" * 74)
    print("1. REDACTION")
    print("=" * 74)
    print("as received:\n ", DIRTY_QUESTION, "\n")
    safe, mapping = redact(DIRTY_QUESTION)
    print("as sent to the model:\n ", safe, "\n")
    print(f"held in-process only ({len(mapping)} items): {list(mapping)}")
    print("  ^ the model never sees these values, so they cannot be logged,")
    print("    cached, or trained on by anyone downstream.\n")

    audit.append(event="request_received", actor=actor,
                 prompt_hash=digest(safe), pii_items=len(mapping))

    print("=" * 74)
    print("2. THE MODEL CALL (on redacted text)")
    print("=" * 74)
    if offline:
        answer = ("Dorm A has 480 residents and Dorm B has 320, for a total of 800. "
                  "I cannot change records; I have proposed the update for approval.")
        print("[--offline] using a canned answer; no API call, no cost.\n")
    else:
        from step3_agent import run as agent          # imported late: --offline needs no key
        answer = await agent(safe)
        print()
    print("answer:", answer, "\n")
    audit.append(event="response_produced", actor=actor,
                 response_hash=digest(answer))

    print("=" * 74)
    print("3. APPROVAL GATE")
    print("=" * 74)
    print(f"read tools the agent may run freely : {sorted(READ_TOOLS)}")
    print(f"write tools that require a human    : {sorted(WRITE_TOOLS)}\n")
    proposal = propose_write("update_resident_count",
                             {"block": "Dorm A", "count": 481}, actor, audit)
    print(proposal)
    token = proposal.split("token ")[1].split(")")[0]
    print(" ", approve_write(token, "supervisor:lim", audit))
    print(" ", approve_write(token, "supervisor:lim", audit), "  <- replay blocked\n")

    print("=" * 74)
    print("4. THE AUDIT CHAIN")
    print("=" * 74)
    ok, detail = audit.verify()
    print(f"verify(): {'OK' if ok else 'TAMPERED'} -- {detail}")
    print(f"log file: {AUDIT_LOG}  (open it -- every line links to the one before)\n")

    print("   Now try breaking it: edit any line in audit-log.jsonl and re-run")
    print("   with --offline. verify() will name the exact line. THAT is what")
    print("   'tamper-evident' buys you, and it is about twenty lines of code.\n")

    print("=" * 74)
    print("5. THE WRITTEN POLICY")
    print("=" * 74)
    print(POLICY)

    print("The point of this module: none of the above is AI-specific, and")
    print("almost none of it is vendor-specific either. It is ordinary")
    print("engineering discipline applied to a new kind of call.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true",
                        help="skip the model call -- inspect the governance mechanics for free")
    args = parser.parse_args()

    if not args.offline and not os.environ.get("GEMINI_API_KEY"):
        raise SystemExit("Set GEMINI_API_KEY, or run with --offline.")
    asyncio.run(main(args.offline))
