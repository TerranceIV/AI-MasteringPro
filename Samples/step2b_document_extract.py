"""
Step 2b Capstone -- DOCUMENTS IN, STRUCTURED DATA OUT.  (module 2.9)

The single most common real-world AI request in an enterprise is some version
of "read these documents and give me structured data." It is also one of the
easiest things to build, because it is just Step 2's structured output (2.6)
with a document block bolted onto the front of the message.

  2.9 a PDF (or image) is a CONTENT BLOCK, not a special API
  2.6 the answer comes back as a VALIDATED Pydantic object, not prose
  1.3 the same model class defines the schema and validates the result

Run:   uv run step2b_document_extract.py                 # uses a generated sample PDF
       uv run step2b_document_extract.py my_form.pdf     # or point it at your own
       uv run step2b_document_extract.py scan.png        # images work identically
Deps:  anthropic pydantic
Env:   ANTHROPIC_API_KEY
"""
import base64
import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from config import EFFORT, MODEL, get_client

client = get_client()

MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
}


# --- 2.6 / 1.3  the shape you want back -------------------------------------
# Every `description` here is sent TO THE MODEL. Treat them as instructions,
# not code comments -- this is the highest-leverage place to be precise.
class InspectionRecord(BaseModel):
    dorm: str = Field(description="Which dormitory block this record is for")
    inspector: str = Field(description="Full name of the inspecting officer")
    inspected_on: str = Field(description="Date of inspection in YYYY-MM-DD form")
    residents: int = Field(description="Total resident headcount stated on the form")
    issues: list[str] = Field(description="Each defect or issue noted, one per item")
    passed: bool = Field(description="True only if the form states the block passed")
    confidence: float = Field(
        ge=0, le=1,
        description="0..1 -- how confident you are. Use a LOW value if the "
                    "document is unclear, partially illegible, or missing fields.",
    )


def extract(path: Path) -> InspectionRecord:
    """Send one document and get a validated object back."""
    media_type = MEDIA_TYPES.get(path.suffix.lower())
    if media_type is None:
        raise SystemExit(f"Unsupported file type {path.suffix!r}. "
                         f"Try one of: {', '.join(sorted(MEDIA_TYPES))}")

    data = base64.standard_b64encode(path.read_bytes()).decode("utf-8")

    # 2.9 PDFs use a "document" block; images use an "image" block. Otherwise
    # they behave the same. Put the file FIRST and the instruction after it --
    # models follow the instruction better when they have already seen the data.
    block_type = "document" if media_type == "application/pdf" else "image"
    file_block = {
        "type": block_type,
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }

    # `messages.parse()` is the shortcut for what step2_first_call.py did by
    # hand: it constrains the output to your schema AND validates it, so
    # `.parsed_output` is already an InspectionRecord instance. Same idea as
    # Step 4's "let the framework do the boilerplate" -- but for one call.
    response = client.messages.parse(
        model=MODEL,
        max_tokens=4096,
        output_config={"effort": EFFORT},
        output_format=InspectionRecord,
        messages=[{
            "role": "user",
            "content": [
                file_block,
                {"type": "text", "text": (
                    "Extract this inspection form into the required structure. "
                    "Use exactly what the document says -- do not infer or "
                    "invent values. If a field is genuinely absent, say so in "
                    "`issues` and lower your `confidence`."
                )},
            ],
        }],
    )
    return response.parsed_output


# --- a real, valid PDF with no third-party library --------------------------
def make_sample_pdf(path: Path) -> None:
    """Write a minimal one-page PDF so this sample runs with zero setup.

    You will never write a PDF by hand in real work -- this exists only so the
    sample has something to read. Skim it and move on.
    """
    lines = [
        "DORMITORY INSPECTION FORM",
        "",
        "Block:            Dorm A",
        "Inspecting officer: Tan Wei Ming",
        "Date of inspection: 2026-08-14",
        "Registered residents: 480",
        "",
        "Findings:",
        "  1. Corridor light out on level 7",
        "  2. Fire extinguisher on level 3 past service date",
        "  3. Laundry room drain partially blocked",
        "",
        "Overall result: FAILED - re-inspection required within 14 days",
    ]

    def esc(s: str) -> str:                     # PDF strings escape ( ) and \
        return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    text_ops = ["BT", "/F1 11 Tf", "14 TL", "50 780 Td"]
    for line in lines:
        text_ops.append(f"({esc(line)}) Tj")
        text_ops.append("T*")                   # next line
    text_ops.append("ET")
    stream = "\n".join(text_ops).encode("latin-1")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))                # byte offset of this object
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"             # every xref entry is exactly 20 bytes
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n".encode()
    out += f"startxref\n{xref_at}\n%%EOF\n".encode()

    path.write_bytes(bytes(out))


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first (see README).")

    if len(sys.argv) > 1:
        target = Path(sys.argv[1])
        if not target.exists():
            raise SystemExit(f"No such file: {target}")
    else:
        target = Path("sample_inspection.pdf")
        if not target.exists():
            make_sample_pdf(target)
            print(f"(generated {target} to have something to read)")

    print(f"reading: {target}")
    record = extract(target)

    print("\nextracted:")
    for field, value in record.model_dump().items():
        print(f"  {field:14} {value}")

    # 6.3 the guardrail that matters most in document extraction: the model is
    # ALWAYS willing to give you an answer, so YOU decide when it isn't good
    # enough to trust. Low confidence should route to a human, never to a
    # database. This one branch is the difference between a demo and a system.
    if record.confidence < 0.8:
        print("\n[!] low confidence -- route this document to a human reviewer")
    else:
        print("\n[ok] confident enough to store automatically")
