"""Versions stamped on every deployment and every decision.

Policy and scorecard versions are bumped by hand when those rules change.
The corpus version is a hash of the policy files, so an edit to the knowledge
base changes the deployment id on the next start.
"""

from __future__ import annotations

import hashlib
import json

from app import __version__
from app.config import KNOWLEDGE_DIR, PD_ENV

POLICY_VERSION = "credit-policy-4.2-2026.10"
SCORECARD_VERSION = "pd-scorecard-reference-3.8-v1"
ML_MODEL_VERSION = "xgboost-crosscheck-v1"
PIPELINE_VERSION = "loan-graph-v1"


def corpus_version() -> str:
    hasher = hashlib.sha256()
    for path in sorted(KNOWLEDGE_DIR.glob("*.md")):
        hasher.update(path.name.encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
    return "corpus-" + hasher.hexdigest()[:12]


def release_manifest() -> dict:
    return {
        "environment": PD_ENV,
        "app_version": __version__,
        "pipeline_version": PIPELINE_VERSION,
        "policy_version": POLICY_VERSION,
        "scorecard_version": SCORECARD_VERSION,
        "ml_model_version": ML_MODEL_VERSION,
        "rag_corpus_version": corpus_version(),
    }


def deployment_id(manifest: dict | None = None) -> str:
    body = manifest or release_manifest()
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"dep-{digest}"
