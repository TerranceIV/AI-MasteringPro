# Gemini learning track

This folder is the Gemini twin of [`../Samples`](../Samples/CLAUDE.md) — same
learner, same teaching goals, different vendor. Everything in that file's
"Who you're talking to" section applies here unchanged: plain language,
explain why not just what, small snippets, point at real `file:line` links,
offer a short experiment.

## Things specific to this folder

- This is a full mirror of `../Samples` (step1 through step6b) except for
  `step2b_document_extract.py` and the prompt-caching lesson inside step3 —
  see README.md's "What's not in this folder" for why those two specifically
  were left out, rather than assuming it's an oversight.
- `step1_mock_agent.py` and `mcp_dorm_server.py` are intentionally
  byte-identical to the Anthropic version's — there is no vendor code in
  either to diverge.
- step5, step5b, step6, and step6b all import step3_agent.py from **this**
  folder (and step5 also imports evals.py from here) — same
  run-from-inside-the-folder rule as `../Samples`.
- Every deliberate divergence from the Claude version is commented at the
  point it happens, and summarized in README.md's diff table. When editing
  or extending this folder, keep that pairing: a difference from `../Samples`
  without a comment explaining *why* is a bug in the teaching material, not
  just the code.
- A few exact SDK call shapes were written from documentation, not run
  locally (see README.md "Honesty check"). If asked to debug an error here,
  check those call sites first before assuming the lesson logic is wrong.
