"""
Step 3b Capstone -- RETRIEVAL QUALITY, MEASURED.  (modules 3.3a / 3.3b)

Most "the agent hallucinated" bugs are really RETRIEVAL MISSES: the model never
saw the right document, so it did its best with what it had. You cannot fix
what you do not measure, so this sample measures retrieval on its own --
separately from the agent, separately from the answer.

Three retrievers, same queries, same labelled answers:
  1. naive keyword  -- what step3_agent.py uses (any word overlaps)
  2. BM25           -- proper lexical ranking (rare words count more)
  3. BM25 + rerank  -- the model re-orders the candidates by real relevance

The honest lesson is in the output: reranking fixes ORDERING, but it can only
reorder what lexical search already found. Queries whose words appear nowhere
in the corpus ("Can I keep a cat?") are unfixable this way -- that specific
failure is what a vector index exists to solve.

Run:   uv run step3b_retrieval.py
Deps:  anthropic pydantic
Env:   ANTHROPIC_API_KEY
"""
import asyncio
import math
import os
import re
from collections import Counter

from pydantic import BaseModel, Field

from config import EFFORT, MODEL, get_client

client = get_client(async_=True)


# --- the corpus -------------------------------------------------------------
# Note the deliberate near-duplicates (laundry / laundry-cost, rent / deposit,
# quiet / noise). Real corpora are full of these, and they are exactly what
# breaks naive retrieval: several documents look plausible for one query.
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

# --- the labelled eval set: query -> the doc ids that SHOULD come back ------
# Writing this by hand IS the work of retrieval evaluation. Twelve labelled
# queries will teach you more than any amount of tuning by vibe. The comment on
# each line is what it is here to prove.
EVALS = [
    ("How many residents live in Dorm A?",    {"dorm-a"}),              # easy
    ("Who handles noise complaints?",         {"noise"}),               # easy
    ("What time must visitors leave?",        {"visitors"}),            # easy
    ("how often is the fire drill",           {"fire"}),                # easy
    ("How much does a laundry wash cost?",    {"laundry-cost"}),        # naive fails, BM25 wins
    ("Is the rent deposit refunded?",         {"deposit"}),             # naive fails, BM25 wins
    ("Do I need a parking permit for a car?", {"parking"}),             # naive fails, BM25 wins
    ("When is monthly rent due?",             {"rent"}),                # near-duplicate distractor
    ("Where can I leave my bicycle?",         {"bicycle"}),             # BM25 mis-RANKS it
    ("residents in Dorm A and Dorm B",        {"dorm-a", "dorm-b"}),    # BM25 mis-RANKS it
    ("Can I keep a cat?",                     {"pets"}),                # lexically impossible
    ("Where do I wash clothes?",              {"laundry"}),             # lexically impossible
]

STOP = {"the", "a", "an", "and", "or", "is", "are", "do", "i", "to", "in", "of",
        "for", "my", "what", "when", "where", "who", "how", "can", "must", "at",
        "be", "on", "by", "it", "does", "get", "there", "any", "need"}


def tokens(text: str) -> list[str]:
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOP]


# --- retriever 1: naive keyword overlap (what step3_agent.py does) ----------
def retrieve_naive(query: str, k: int = 3) -> list[str]:
    qs = set(tokens(query))
    hits = [doc_id for doc_id, text in DOCS.items() if qs & set(tokens(text))]
    return hits[:k]          # note: NO ranking at all -- dict order decides


# --- retriever 2: BM25 ------------------------------------------------------
# BM25 is the lexical baseline you should always beat before reaching for
# anything fancier. Two ideas do all the work:
#   * a word that appears in FEW documents is more informative (IDF)
#   * a word appearing 10 times isn't 10x more relevant (saturation, via k1)
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
class Ranking(BaseModel):
    doc_ids: list[str] = Field(
        description="The candidate doc ids, re-ordered most relevant first. "
                    "Drop any candidate that does not actually answer the query."
    )


async def retrieve_reranked(query: str, k: int = 3, candidates: int = 6) -> list[str]:
    """Cast a WIDE lexical net, then let the model pick the best few.

    This two-stage shape -- cheap recall, then expensive precision -- is how
    most good retrieval systems are built. The reranker sees far fewer documents
    than the corpus, so it stays affordable.
    """
    pool = retrieve_bm25(query, k=candidates)
    if len(pool) <= 1:
        return pool                       # nothing to reorder

    listing = "\n".join(f"{d}: {DOCS[d]}" for d in pool)
    response = await client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        output_config={"effort": "low"},   # reranking is a cheap, narrow judgement
        output_format=Ranking,
        messages=[{"role": "user", "content": (
            f"Query: {query}\n\nCandidate documents:\n{listing}\n\n"
            "Order the candidate ids by how well each ANSWERS the query. "
            "Omit candidates that are merely on a similar topic."
        )}],
    )
    ranked = [d for d in response.parsed_output.doc_ids if d in DOCS]
    return ranked[:k]


# --- scoring ----------------------------------------------------------------
def recall_at_k(got: list[str], want: set[str], k: int) -> float:
    """Fraction of the wanted docs that appear in the top k."""
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
Read the table, not just the averages. Three lessons, in order of how much
money they save you:

1. THE BIGGEST WIN IS THE CHEAPEST. Going from naive overlap to BM25 costs you
   thirty lines of arithmetic, no API calls, and no database -- and it fixes
   most of the failures here (look at "laundry wash cost", "rent deposit",
   "parking permit"). Naive retrieval doesn't rank at all, so the right document
   is in the pile but not at the top. Fix your lexical baseline BEFORE you shop
   for infrastructure.

2. RERANKING FIXES ORDER, NOT RECALL. Where BM25@3 found the document but
   BM25@1 put something else first ("bicycle", "Dorm A and Dorm B"), the model
   reorders it correctly. That is a real win, and it is genuinely modest on a
   small clean corpus -- it grows as your corpus gets messier. Note that
   reranking cannot rescue what was never retrieved: where BM25@3 is 0.00,
   rerank is 0.00 too.

3. THE LAST GAP IS THE ONLY ONE THAT JUSTIFIES A VECTOR DATABASE. "Can I keep a
   cat?" and "Where do I wash clothes?" fail at every stage because the words
   "cat" and "clothes" appear nowhere in the corpus. No amount of lexical
   tuning finds them. THIS specific failure -- vocabulary mismatch between how
   users ask and how documents are written -- is what embeddings exist to solve,
   and it is the only honest reason to add one.

And the meta-lesson: none of the above was arguable, because it was measured.
Twelve labelled queries turned "our RAG feels bad" into three named problems
with three different fixes. That is the whole point of module 3.3b.
""")


if __name__ == "__main__":
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first (see README).")
    asyncio.run(main())
