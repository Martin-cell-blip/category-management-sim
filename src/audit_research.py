"""Validate the structured research evidence layer and emit audit artifacts."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
DOCS = ROOT / "docs" / "research"


def _ids(value: object) -> set[str]:
    if pd.isna(value) or not str(value).strip():
        return set()
    return {part.strip() for part in str(value).split(";") if part.strip()}


def audit() -> dict:
    sources = pd.read_csv(RESEARCH / "sources.csv")
    claims = pd.read_csv(RESEARCH / "claims.csv")
    contradictions = pd.read_csv(RESEARCH / "contradictions.csv")
    gaps = pd.read_csv(RESEARCH / "data_gaps.csv")
    assumptions = json.loads((RESEARCH / "assumptions.json").read_text(encoding="utf-8"))
    frames = {
        "sources": (sources, "source_id"),
        "claims": (claims, "claim_id"),
        "contradictions": (contradictions, "contradiction_id"),
        "data_gaps": (gaps, "gap_id"),
    }
    errors: list[str] = []
    for name, (frame, id_col) in frames.items():
        if frame[id_col].isna().any() or frame[id_col].duplicated().any():
            errors.append(f"{name}.{id_col} 存在空值或重复")
    source_ids = set(sources["source_id"])
    assumption_ids = {row["assumption_id"] for row in assumptions}
    for row in claims.itertuples(index=False):
        refs = _ids(row.source_ids)
        assumptions_used = _ids(row.assumption_ids)
        if not refs and not assumptions_used:
            errors.append(f"{row.claim_id} 无来源且无假设")
        if refs - source_ids:
            errors.append(f"{row.claim_id} 引用了未知来源 {sorted(refs - source_ids)}")
        if assumptions_used - assumption_ids:
            errors.append(
                f"{row.claim_id} 引用了未知假设 {sorted(assumptions_used - assumption_ids)}"
            )
    if sources["url"].isna().any() or (sources["url"].str.strip() == "").any():
        errors.append("sources.csv 存在空 URL")
    expected = {"contradictions": 6, "data_gaps": 14, "assumptions": 7}
    actual = {
        "contradictions": len(contradictions),
        "data_gaps": len(gaps),
        "assumptions": len(assumptions),
    }
    if actual != expected:
        errors.append(f"证据台账数量不符: expected={expected}, actual={actual}")
    return {
        "status": "passed" if not errors else "failed",
        "counts": {
            "claims": len(claims),
            "sources": len(sources),
            **actual,
        },
        "errors": errors,
    }


def main() -> None:
    result = audit()
    if result["errors"]:
        raise SystemExit("\n".join(result["errors"]))
    DOCS.mkdir(parents=True, exist_ok=True)
    files = sorted(RESEARCH.glob("*"))
    manifest = {
        "manifest_version": "research-evidence-v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        **result,
        "files": [
            {
                "path": path.relative_to(ROOT).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for path in files
            if path.is_file()
        ],
    }
    (DOCS / "research_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    summary = [
        "# 行业研究证据审计摘要",
        "",
        f"- 状态：{result['status']}",
        f"- 核心主张：{result['counts']['claims']} 条",
        f"- 结构化来源：{result['counts']['sources']} 条（完整展示稿另含 100+ 条参考资料）",
        f"- 显式假设：{result['counts']['assumptions']} 条",
        f"- 口径矛盾：{result['counts']['contradictions']} 条",
        f"- 数据缺口：{result['counts']['data_gaps']} 条",
        "",
        "展示稿仍位于 `index.html`；本目录的 manifest 与 `research/` 台账负责机器可审计性。",
    ]
    (DOCS / "audit_summary.md").write_text("\n".join(summary) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
