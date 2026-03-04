# TODO: Instruction-Prefixed Embeddings

Add support for **asymmetric instruction-prefixed embeddings** as an option in the
embeddings service.

## Background

Current embeddings use `all-MiniLM-L6-v2` (or equivalent) with symmetric,
general-purpose encoding — the same prompt for both queries and documents.

LinkedIn's production news classifier uses **LE5** (LLM Encoder for Retrieval and
Ranking) with task-specific instruction prefixes that differ between the query
(post text) and the document (article title + body):

```
query:    "Instruct: Given a LinkedIn post, retrieve relevant articles.\nQuery: Post Text: <text>"
document: "Instruct: Given a LinkedIn post, retrieve relevant articles.\nPassage: ArticleTitle ArticleText: <text>"
```

This asymmetric approach — pioneered by E5-instruct / Instructor-XL — conditions the
embedding space on the retrieval task, producing meaningfully better separation between
matched and unmatched pairs, especially when query and document are stylistically different
(short informal post vs. long formal article).

## What to implement

- Add a `mode` or `prompt_template` parameter to the embeddings endpoint (headwater or
  siphon-server) that accepts an optional instruction prefix per role (`query`, `document`).
- Default behavior (no prefix) should be unchanged.
- Candidate open-weight models that support this natively:
  - `intfloat/e5-large-v2` / `intfloat/multilingual-e5-large-instruct`
  - `hkunlp/instructor-xl`
  - `BAAI/bge-large-en-v1.5` (with `Represent this sentence for searching relevant passages:` prefix)
- Reference: [E5 paper](https://arxiv.org/abs/2212.03533),
  [Instructor paper](https://arxiv.org/abs/2212.09561)

## Motivation

Discovered while studying LinkedIn's RFC for news classification (2026-03-01).
The current symmetric embeddings are adequate for general semantic similarity;
instruction-prefixed embeddings are the right tool for asymmetric retrieval tasks
where query and document have different structure or register.
