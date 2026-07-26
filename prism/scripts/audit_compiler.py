#!/usr/bin/env python3
"""Audit compile_schema_v1 against every real schema Prism has: the 2
pilot tools + all 18 real BFCL GorillaFileSystem functions. Reports,
per field: whether a constraint clause exists, and whether the OLD
(35/70-char blunt cap) compiler would have cut it — vs the NEW
(clause-aware) compiler, which must never cut a constraint clause.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from harness.runner import compile_schema_v1, RAW_SCHEMAS, _is_load_bearing


def old_trim(text, cap):
    """The v1.0 logic, reproduced here ONLY for the audit comparison —
    not imported, since v1.0 no longer exists in runner.py (superseded,
    not kept as dead code)."""
    if not text:
        return text
    first = text.split(".")[0].strip()
    if len(first) <= cap:
        return first + "."
    return (first[:cap].rsplit(" ", 1)[0] or first[:cap]) + "…"


def audit_one(name, schema):
    rows = []
    fields = [("description", schema.get("description", ""))]
    for pname, p in schema.get("parameters", {}).get("properties", {}).items():
        fields.append((f"param:{pname}", p.get("description", "")))
    cap = {"description": 70}
    for field, text in fields:
        if not text:
            continue
        c = cap.get(field, 35)
        clauses = [x.strip() for x in text.split(". ") if x.strip()]
        constraint_clauses = [x for x in clauses[1:] if _is_load_bearing(x)]
        old_out = old_trim(text, c)
        old_lost_constraint = any(
            cc.rstrip(".") not in old_out for cc in constraint_clauses)
        rows.append({
            "schema": name, "field": field,
            "has_constraint": bool(constraint_clauses),
            "v1.0_would_lose_it": old_lost_constraint and bool(constraint_clauses),
        })
    return rows


def main():
    all_schemas = [(name, s) for name, s in RAW_SCHEMAS.items()]
    bfcl_path = (Path(__file__).resolve().parent.parent / "suite" / "w2_staging"
                / "bfcl_extracted.json")
    if bfcl_path.exists():
        bfcl = json.loads(bfcl_path.read_text())
        for s in bfcl["tasks"][0]["tool_schemas"]:
            all_schemas.append((s["name"], s))

    audit_rows = []
    total_raw, total_v11 = 0, 0
    for name, schema in all_schemas:
        audit_rows.extend(audit_one(name, schema))
        c = compile_schema_v1(schema)
        total_raw += len(json.dumps(schema))
        total_v11 += len(json.dumps(c, separators=(",", ":")))

    at_risk = [r for r in audit_rows if r["v1.0_would_lose_it"]]
    with_constraint = [r for r in audit_rows if r["has_constraint"]]

    print(f"schemas audited: {len(all_schemas)}")
    print(f"fields with a constraint clause: {len(with_constraint)}")
    print(f"fields where v1.0's blunt cap WOULD have cut the constraint: "
          f"{len(at_risk)}")
    for r in at_risk:
        print(f"  AT RISK under v1.0: {r['schema']}.{r['field']}")

    # Prove v1.2 never loses one, on the real data
    lost_under_v11 = 0
    for name, schema in all_schemas:
        c = compile_schema_v1(schema)
        fields = [("description", schema.get("description", ""), c.get("description", ""))]
        for pname, p in schema.get("parameters", {}).get("properties", {}).items():
            fields.append((f"param:{pname}", p.get("description", ""),
                          c.get("parameters", {}).get("properties", {})
                           .get(pname, {}).get("description", "")))
        for field, before, after in fields:
            if not before:
                continue
            clauses = [x.strip() for x in before.split(". ") if x.strip()]
            for cc in clauses[1:]:
                if _is_load_bearing(cc) and cc.rstrip(".") not in after:
                    lost_under_v11 += 1
                    print(f"  STILL LOST under v1.2 (BUG): {name}.{field}: {cc!r}")

    print(f"\nload-bearing clauses lost under v1.2: {lost_under_v11} (must be 0)")
    print(f"\ncompression, honest trade-off: {total_raw}B -> {total_v11}B "
          f"({100*(1-total_v11/total_raw):.0f}% smaller, vs v1.0's ~58% — "
          f"the gap is the cost of never dropping a constraint)")
    assert lost_under_v11 == 0, "v1.2 regression: a load-bearing clause was lost"


if __name__ == "__main__":
    main()
