#!/usr/bin/env python3
"""Run an offline retrieval benchmark over the local fixture corpus."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from openai_docs_scraper.book_export import rel_md_path_from_url
from openai_docs_scraper.db import connect, init_db
from openai_docs_scraper.embeddings import normalize_vec, pack_f32
from openai_docs_scraper.ingest_cached import ingest_cached_pages
from openai_docs_scraper.ranking import RankingCandidate, rank_candidates
from openai_docs_scraper.search import vector_search_chunks, vector_search_pages
from openai_docs_scraper.services.search import query as fts_query


DEFAULT_CORPUS_DIR = Path("evals/corpus/raw_pages")
DEFAULT_BENCHMARK_PATH = Path("evals/benchmarks/openai_docs_benchmark.json")
DEFAULT_OUTPUT_PATH = Path("evals/results/latest_local.json")
DEFAULT_BASELINE_PATH = Path("evals/results/baseline_local.json")
LOCAL_EMBEDDING_MODEL = "local-hash-v1"
EMBED_DIM = 256


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _char_ngrams(text: str, n: int = 3) -> list[str]:
    cleaned = re.sub(r"[^a-z0-9]+", "", (text or "").lower())
    if len(cleaned) < n:
        return [cleaned] if cleaned else []
    return [cleaned[i : i + n] for i in range(len(cleaned) - n + 1)]


def _local_embedding(text: str, *, dim: int = EMBED_DIM) -> list[float]:
    counts: Counter[int] = Counter()
    for token in _tokenize(text):
        digest = sha256(f"tok:{token}".encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1 if digest[4] % 2 == 0 else -1
        counts[idx] += sign
    for gram in _char_ngrams(text):
        digest = sha256(f"chr:{gram}".encode("utf-8")).digest()
        idx = int.from_bytes(digest[:4], "big") % dim
        sign = 1 if digest[4] % 2 == 0 else -1
        counts[idx] += sign
    vec = [0.0] * dim
    for idx, value in counts.items():
        vec[idx] = float(value)
    normalized = normalize_vec(np.asarray(vec, dtype="float32"))
    return normalized.astype("float32", copy=False).tolist()


def _seed_page_summaries_and_embeddings(con, corpus_dir: Path) -> None:
    for path in sorted(corpus_dir.glob("*.json")):
        obj = _load_json(path)
        url = str(obj["url"])
        summary = str(obj.get("summary") or "").strip()
        row = con.execute(
            "SELECT id, content_hash FROM pages WHERE url = ?;",
            (url,),
        ).fetchone()
        if row is None:
            continue
        con.execute(
            """
            UPDATE pages
            SET summary = ?,
                summary_model = ?,
                summary_updated_at = ?,
                summary_for_hash = ?,
                embedding = ?,
                embedding_model = ?,
                embedding_updated_at = ?,
                embedding_for_hash = ?
            WHERE id = ?;
            """,
            (
                summary,
                "fixture-summary",
                _utc_now(),
                row["content_hash"],
                pack_f32(_local_embedding(summary)),
                LOCAL_EMBEDDING_MODEL,
                _utc_now(),
                row["content_hash"],
                row["id"],
            ),
        )
    rows = con.execute("SELECT id, chunk_text, chunk_hash FROM chunks;").fetchall()
    for row in rows:
        con.execute(
            """
            UPDATE chunks
            SET embedding = ?,
                embedding_model = ?,
                embedding_updated_at = ?,
                embedding_for_hash = ?
            WHERE id = ?;
            """,
            (
                pack_f32(_local_embedding(str(row["chunk_text"] or ""))),
                LOCAL_EMBEDDING_MODEL,
                _utc_now(),
                row["chunk_hash"],
                row["id"],
            ),
        )
    con.commit()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fts_hits(db_path: Path, query_text: str, k: int) -> list[dict[str, Any]]:
    hits = fts_query(
        db_path=db_path,
        q=query_text,
        k=k,
        no_embed=True,
        target="chunks",
        group_pages=True,
    )
    out: list[dict[str, Any]] = []
    for hit in hits:
        out.append(
            {
                "url": hit.url,
                "title": hit.title,
                "summary": hit.summary,
                "score": float(hit.score),
                "md_relpath": hit.md_relpath,
            }
        )
    return out


def _rank_mode(
    query_text: str,
    *,
    vector_rows: list[dict[str, Any]],
    lexical_rows: list[dict[str, Any]],
    k: int,
) -> list[dict[str, Any]]:
    merged: dict[str, RankingCandidate] = {}
    for row in vector_rows:
        merged[row["url"]] = RankingCandidate(
            url=row["url"],
            title=row.get("title"),
            summary=row.get("summary"),
            chunk_text=row.get("chunk_text", "") or "",
            source_path=row.get("source_path"),
            md_relpath=row["md_relpath"],
            vector_raw=float(row["score"]),
        )
    for row in lexical_rows:
        existing = merged.get(row["url"])
        if existing is None:
            merged[row["url"]] = RankingCandidate(
                url=row["url"],
                title=row.get("title"),
                summary=row.get("summary"),
                chunk_text=row.get("chunk_text", "") or "",
                source_path=row.get("source_path"),
                md_relpath=row["md_relpath"],
                lexical_raw=float(row["score"]),
            )
            continue
        existing.lexical_raw = float(row["score"])
        if row.get("chunk_text"):
            existing.chunk_text = row["chunk_text"]
        if row.get("summary"):
            existing.summary = row["summary"]

    ranked = rank_candidates(query_text, list(merged.values()), limit=k)
    return [
        {
            "url": candidate.url,
            "title": candidate.title,
            "summary": candidate.summary,
            "score": candidate.score,
            "md_relpath": candidate.md_relpath,
            "score_details": candidate.score_details,
        }
        for candidate in ranked
    ]


def _page_vector_hits(con, query_text: str, k: int) -> list[dict[str, Any]]:
    hits = vector_search_pages(con=con, query_embedding=_local_embedding(query_text), limit=max(k * 5, 20))
    rows = [
        {
            "url": hit.url,
            "title": hit.title,
            "summary": hit.summary,
            "chunk_text": hit.summary or "",
            "score": float(hit.score),
            "md_relpath": rel_md_path_from_url(hit.url).as_posix(),
        }
        for hit in hits
    ]
    return _rank_mode(query_text, vector_rows=rows, lexical_rows=[], k=k)


def _chunk_vector_hits(con, query_text: str, k: int, *, hybrid: bool = False, db_path: Path | None = None) -> list[dict[str, Any]]:
    hits = vector_search_chunks(
        con=con,
        query_embedding=_local_embedding(query_text),
        limit=max(k * 5, 20),
        fts_query=None,
    )
    best_by_url: dict[str, dict[str, Any]] = {}
    for hit in hits:
        row = {
            "url": hit.url,
            "title": hit.title,
            "summary": hit.summary,
            "chunk_text": hit.chunk_text,
            "score": float(hit.score),
            "md_relpath": rel_md_path_from_url(hit.url).as_posix(),
        }
        prev = best_by_url.get(hit.url)
        if prev is None or row["score"] > prev["score"]:
            best_by_url[hit.url] = row
    lexical_rows = _fts_hits(db_path, query_text, max(k * 5, 20)) if hybrid and db_path is not None else []
    return _rank_mode(query_text, vector_rows=list(best_by_url.values()), lexical_rows=lexical_rows, k=k)


def _rank_of_first_expected(hits: list[dict[str, Any]], expected_urls: list[str]) -> int | None:
    expected = set(expected_urls)
    for index, hit in enumerate(hits, start=1):
        if hit["url"] in expected:
            return index
    return None


def _metrics(per_query: list[dict[str, Any]], *, max_k: int = 5) -> dict[str, Any]:
    total = len(per_query)
    ranks = [item["first_relevant_rank"] for item in per_query]
    hit_at_1 = sum(1 for rank in ranks if rank == 1)
    hit_at_3 = sum(1 for rank in ranks if rank is not None and rank <= 3)
    hit_at_5 = sum(1 for rank in ranks if rank is not None and rank <= max_k)
    mrr = sum(0.0 if rank is None else 1.0 / rank for rank in ranks) / total if total else 0.0
    return {
        "queries": total,
        "hit_rate_at_1": round(hit_at_1 / total, 4) if total else 0.0,
        "recall_at_3": round(hit_at_3 / total, 4) if total else 0.0,
        "recall_at_5": round(hit_at_5 / total, 4) if total else 0.0,
        "mrr_at_5": round(mrr, 4),
    }


def _build_eval_db(corpus_dir: Path, db_path: Path) -> None:
    con = connect(db_path)
    init_db(con)
    ingest_cached_pages(con=con, raw_dir=corpus_dir, force=True)
    _seed_page_summaries_and_embeddings(con, corpus_dir)
    con.close()


def _run_benchmark(corpus_dir: Path, benchmark_path: Path, *, k: int) -> dict[str, Any]:
    benchmark = _load_json(benchmark_path)
    with TemporaryDirectory(prefix="openai-docs-eval-") as tmpdir:
        db_path = Path(tmpdir) / "eval.sqlite3"
        _build_eval_db(corpus_dir, db_path)
        con = connect(db_path)
        init_db(con)

        modes = {
            "fts": lambda q: _fts_hits(db_path, q, k),
            "page_vector": lambda q: _page_vector_hits(con, q, k),
            "chunk_vector": lambda q: _chunk_vector_hits(con, q, k, hybrid=False, db_path=db_path),
            "hybrid": lambda q: _chunk_vector_hits(con, q, k, hybrid=True, db_path=db_path),
        }

        results_by_mode: dict[str, dict[str, Any]] = {}
        for mode_name, fn in modes.items():
            per_query: list[dict[str, Any]] = []
            for item in benchmark["queries"]:
                hits = fn(item["query"])
                rank = _rank_of_first_expected(hits, item["expected_urls"])
                per_query.append(
                    {
                        "id": item["id"],
                        "query": item["query"],
                        "expected_urls": item["expected_urls"],
                        "first_relevant_rank": rank,
                        "top_hits": hits,
                    }
                )
            results_by_mode[mode_name] = {
                "metrics": _metrics(per_query, max_k=k),
                "per_query": per_query,
            }

        corpus_stats = {
            "pages": int(con.execute("SELECT COUNT(*) FROM pages;").fetchone()[0]),
            "chunks": int(con.execute("SELECT COUNT(*) FROM chunks;").fetchone()[0]),
        }
        con.close()

    return {
        "generated_at": _utc_now(),
        "embedding_model": LOCAL_EMBEDDING_MODEL,
        "benchmark": {
            "name": benchmark["name"],
            "description": benchmark.get("description", ""),
            "query_count": len(benchmark["queries"]),
        },
        "corpus": {
            "path": str(corpus_dir),
            **corpus_stats,
        },
        "results": results_by_mode,
    }


def _print_summary(report: dict[str, Any], baseline: dict[str, Any] | None = None) -> None:
    print(f"Benchmark: {report['benchmark']['name']}")
    print(f"Queries: {report['benchmark']['query_count']}")
    print(f"Corpus pages: {report['corpus']['pages']}, chunks: {report['corpus']['chunks']}")
    print("")
    for mode_name, payload in report["results"].items():
        metrics = payload["metrics"]
        print(
            f"{mode_name:12} "
            f"hit@1={metrics['hit_rate_at_1']:.4f} "
            f"recall@3={metrics['recall_at_3']:.4f} "
            f"recall@5={metrics['recall_at_5']:.4f} "
            f"mrr@5={metrics['mrr_at_5']:.4f}"
        )
        if baseline is not None and mode_name in baseline.get("results", {}):
            prev = baseline["results"][mode_name]["metrics"]
            delta = metrics["mrr_at_5"] - prev["mrr_at_5"]
            print(f"  delta mrr@5={delta:+.4f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local retrieval benchmark.")
    parser.add_argument("--corpus-dir", default=str(DEFAULT_CORPUS_DIR))
    parser.add_argument("--benchmark", default=str(DEFAULT_BENCHMARK_PATH))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_PATH))
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--compare-baseline",
        action="store_true",
        help="Compare the current report to an existing baseline file.",
    )
    parser.add_argument(
        "--baseline",
        default=str(DEFAULT_BASELINE_PATH),
        help="Baseline report path used with --compare-baseline.",
    )
    args = parser.parse_args()

    corpus_dir = Path(args.corpus_dir)
    benchmark_path = Path(args.benchmark)
    output_path = Path(args.output)

    report = _run_benchmark(corpus_dir, benchmark_path, k=args.k)
    baseline = None
    if args.compare_baseline:
        baseline_path = Path(args.baseline)
        if baseline_path.is_file():
            baseline = _load_json(baseline_path)
    _print_summary(report, baseline=baseline)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nWrote report to {output_path}")


if __name__ == "__main__":
    main()
