"""Local RAG index over the policy corpus.

Vectors are TF-IDF, fit on this machine from the markdown knowledge files.
Nothing is sent to an embedding API.
"""

from __future__ import annotations

import re
from functools import lru_cache

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from app.config import KNOWLEDGE_DIR

SOURCE_NAMES = {
    "credit_policy": "Credit Policy",
    "lending_guidelines": "Lending Guidelines",
    "risk_policy": "Risk Policy",
    "regulatory_notes": "Regulatory Notes",
    "historical_decisions": "Historical Decisions",
}
SECTION_RE = re.compile(r"§\d+(?:\.\d+)*|HD-\d+")


def _parse_markdown(path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    source = SOURCE_NAMES.get(path.stem, path.stem.replace("_", " ").title())
    chunks = []
    for part in re.split(r"(?m)^(?=## )", text):
        part = part.strip()
        if not part.startswith("## "):
            continue
        heading, _, body = part.partition("\n")
        title = heading[3:].strip()
        found = SECTION_RE.search(title)
        section = found.group(0) if found else title
        body = body.strip()
        excerpt = body if len(body) <= 700 else body[:697].rstrip() + "..."
        chunks.append(
            {
                "source": source,
                "section": section,
                "title": title,
                "text": body,
                "excerpt": excerpt,
            }
        )
    return chunks


class KnowledgeIndex:
    def __init__(self, chunks: list[dict], vectorizer: TfidfVectorizer, matrix):
        self.chunks = chunks
        self.vectorizer = vectorizer
        self.matrix = matrix

    def __len__(self) -> int:
        return len(self.chunks)

    def get(self, section: str) -> dict | None:
        for chunk in self.chunks:
            if chunk["section"] == section:
                return chunk
        return None

    def search(self, query: str, k: int = 4) -> list[dict]:
        if not self.chunks or not query.strip():
            return []
        query_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(query_vec, self.matrix).ravel()
        order = scores.argsort()[::-1]
        hits = []
        for index in order:
            if scores[index] <= 0:
                continue
            item = dict(self.chunks[int(index)])
            item["score"] = round(float(scores[index]), 4)
            hits.append(item)
            if len(hits) >= k:
                break
        return hits


@lru_cache(maxsize=1)
def get_index() -> KnowledgeIndex:
    chunks: list[dict] = []
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        chunks.extend(_parse_markdown(path))
    if not chunks:
        raise FileNotFoundError(f"No policy documents in {KNOWLEDGE_DIR}")
    corpus = [f"{chunk['title']}\n{chunk['text']}" for chunk in chunks]
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    matrix = vectorizer.fit_transform(corpus)
    return KnowledgeIndex(chunks, vectorizer, matrix)
