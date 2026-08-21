"""
Step 3b Capstone (Gemini twin) -- RETRIEVAL QUALITY, MEASURED. (modules 3.3a / 3.3b)

Same lesson as ../Samples/step3b_retrieval.py, same corpus, same 12 labelled
queries. Retrieval itself (naive keyword overlap, BM25) is plain Python --
there is no vendor in it at all. Only the THIRD retriever changes: it asks a
model to rerank candidates, and that one call is where the Gemini/Claude diff
shows up.

The honest lesson is unchanged: reranking fixes ORDERING, not RECALL. Queries
whose words appear nowhere in the corpus ("Can I keep a cat?") stay
unfixable by any of the three retrievers here -- that specific failure is
what a vector index exists to solve.

Run:   uv run step3b_retrieval.py
Deps:  google-genai pydantic
Env:   GEMINI_API_KEY
"""
import asyncio
import math
import re
from collections import Counter

from google.genai import types
from pydantic import BaseModel, Field

from config import MODEL, get_client

client = get_client()


# --- the corpus (identical to ../Samples/step3b_retrieval.py) ---------------
DOCS = {
    "dorm-a":       "Dorm A has 12 floors and houses 480 residents.",
    "dorm-b":       "Dorm B has 8 floors and houses 320 residents.",
    "dorm-c":       "Dorm C has 10 floors and houses 400 residents.",
    "quiet":        "Quiet hours are 10pm to 7am across all dormitory blocks.",
    "noise":        "Noise complaints during quiet hours go to the duty warden on level 1.",
    "laundry":      "Laundry rooms are on level 1 of each block and close at 11pm.",
    "laundry-cost": "Each laundry wash costs two dollars, payable by stored value card.",
    "visitors":     "Visitors must be registered at the front desk and leave by 10pm.",
    "overnight":    "Overnight guests are not allowed in any dormitory block.",
    "maintenance":  "Report a fault by raising a ticket with the estate office.",
    "electrical":   "Urgent electrical faults are attended to within 4 hours.",
    "fire":         "Fire drills are held quarterly; residents assemble at the open car park.",
    "rent":         "Monthly rent is charged on the first of each month, due within 14 days.",
    "deposit":      "A security deposit of one month rent is refunded on move out.",
    "wifi":         "Wireless network access is free; the password rotates every semester.",
    "parking":      "Parking permit holders must display a valid vehicle registration.",
    "bicycle":      "Bicycle racks are provided at each block entrance at no charge.",
    "pets":         "Pets are not permitted in any block except registered assistance animals.",
}

EVALS = [
    ("How many residents live in Dorm A?",    {"dorm-a"}),
    ("Who handles noise complaints?",         {"noise"}),
    ("What time must visitors leave?",        {"visitors"}),
    ("how often is the fire drill",           {"fire"}),
    ("How much does a laundry wash cost?",    {"laundry-cost"}),
    ("Is the rent deposit refunded?",         {"deposit"}),
    ("Do I need a parking permit for a car?", {"parking"}),
    ("When is monthly rent due?",             {"rent"}),
    ("Where can I leave my bicycle?",         {"bicycle"}),
    ("residents in Dorm A and Dorm B",        {"dorm-a", "dorm-b"}),
    ("Can I keep a cat?",                     {"pets"}),
    ("Where do I wash clothes?",              {"laundry"}),
]

STOP = {"the", "a", "an", "and", "or", "is", "are", "do", "i", "to", "in", "of",
        "for", "my", "what", "when", "where", "who", "how", "can", "must", "at",
        "be", "on", "by", "it", "does", "get", "there", "any", "need"}


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


def retrieve_naive(query: str, k: int = 3) -> list[str]:
    qs = set(tokens(query))
    hits = [doc_id for doc_id, text in DOCS.items() if qs & set(tokens(text))]
    return hits[:k]


K1, B = 1.5, 0.75
_DOC_TOKENS = {d: tokens(t) for d, t in DOCS.items()}
_AVG_LEN = sum(len(t) for t in _DOC_TOKENS.values()) / len(_DOC_TOKENS)
_DF = Counter(w for toks in _DOC_TOKENS.values() for w in set(toks))
_N = len(_DOC_TOKENS)


def bm25_score(query_tokens: list[str], doc_id: str) -> float:
    toks = _DOC_TOKENS[doc_id]
    freq, length, score = Counter(toks), len(toks), 0.0
    for w in query_tokens:
        if w not in freq:
            continue
        idf = math.log(1 + (_N - _DF[w] + 0.5) / (_DF[w] + 0.5))
        tf = freq[w] * (K1 + 1) / (freq[w] + K1 * (1 - B + B * length / _AVG_LEN))
        score += idf * tf
    return score


def retrieve_bm25(query: str, k: int = 3) -> list[str]:
    qs = tokens(query)
    scored = [(bm25_score(qs, d), d) for d in DOCS]
    scored = [(s, d) for s, d in scored if s > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [d for _, d in scored[:k]]


# --- retriever 3: BM25 candidates, reranked by the model --------------------
# Claude's version forces this through a tool call and parses the tool_use
# block by hand (messages.parse). Gemini has a native response_schema mode --
# no forcing needed, and thinking_budget=0 keeps this cheap: reranking is a
# narrow judgement call, and Flash models let you disable thinking entirely
# rather than just dialing it down the way Claude's `effort="low"` does.
class Ranking(BaseModel):
    doc_ids: list[str] = Field(
        description="The candidate doc ids, re-ordered most relevant first. "
                    "Drop any candidate that does not actually answer the query."
    )


async def retrieve_reranked(query: str, k: int = 3, candidates: int = 6) -> list[str]:
    pool = retrieve_bm25(query, k=candidates)
    if len(pool) <= 1:
        return pool

    listing = "\n".join(f"{d}: {DOCS[d]}" for d in pool)
    response = await client.aio.models.generate_content(
        model=MODEL,
        contents=(
            f"Query: {query}\n\nCandidate documents:\n{listing}\n\n"
            "Order the candidate ids by how well each ANSWERS the query. "
            "Omit candidates that are merely on a similar topic."
        ),
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Ranking,
            thinking_config=types.ThinkingConfig(thinking_budget=0),
        ),
    )
    ranked = [d for d in response.parsed.doc_ids if d in DOCS]
    return ranked[:k]


def recall_at_k(got: list[str], want: set[str], k: int) -> float:
    return len(set(got[:k]) & want) / len(want)


async def main() -> None:
    rows = []
    for query, want in EVALS:
        naive = retrieve_naive(query, k=3)
        bm25 = retrieve_bm25(query, k=3)
        rerank = await retrieve_reranked(query, k=3)
        rows.append((query, want, naive, bm25, rerank))

    print(f"{'query':<34} {'naive@1':>8} {'bm25@1':>8} {'rerank@1':>9}   top hit after rerank")
    print("-" * 100)
    totals = {"naive": 0.0, "bm25": 0.0, "rerank": 0.0}
    totals3 = {"naive": 0.0, "bm25": 0.0, "rerank": 0.0}

    for query, want, naive, bm25, rerank in rows:
        r = {"naive": recall_at_k(naive, want, 1),
             "bm25": recall_at_k(bm25, want, 1),
             "rerank": recall_at_k(rerank, want, 1)}
        for name in totals:
            totals[name] += r[name]
        totals3["naive"] += recall_at_k(naive, want, 3)
        totals3["bm25"] += recall_at_k(bm25, want, 3)
        totals3["rerank"] += recall_at_k(rerank, want, 3)
        top = rerank[0] if rerank else "-- nothing retrieved --"
        print(f"{query[:33]:<34} {r['naive']:>8.2f} {r['bm25']:>8.2f} "
              f"{r['rerank']:>9.2f}   {top}")

    n = len(rows)
    print("-" * 100)
    print(f"{'MEAN RECALL@1':<34} {totals['naive']/n:>8.2f} {totals['bm25']/n:>8.2f} "
          f"{totals['rerank']/n:>9.2f}")
    print(f"{'MEAN RECALL@3':<34} {totals3['naive']/n:>8.2f} {totals3['bm25']/n:>8.2f} "
          f"{totals3['rerank']/n:>9.2f}")

    print("""
Same three lessons as the Claude version, because none of them are about the
vendor:

1. THE BIGGEST WIN IS THE CHEAPEST -- naive to BM25 costs thirty lines of
   arithmetic and zero API calls.
2. RERANKING FIXES ORDER, NOT RECALL -- it cannot rescue what BM25 never
   retrieved.
3. THE LAST GAP IS THE ONLY ONE THAT JUSTIFIES A VECTOR DATABASE -- "cat" and
   "clothes" appear nowhere in the corpus, and no lexical tuning finds them.

The meta-lesson also survives the vendor swap: measure retrieval on its own,
separately from the model, and vague complaints turn into named problems.
""")


if __name__ == "__main__":
    asyncio.run(main())
