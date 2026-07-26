#!/usr/bin/env python3
"""Promote reviewed PT drafts into the real, runnable suite fields.

Workflow: edit prism/suite/w2_staging/{gsm8k,bfcl}_pt_draft.json
directly — the pt_draft / turns_pt_draft fields — fixing anything
that's a genuine translation defect. Leave a task's draft untouched if
it reads correctly as-is (per the pilot findings, most will — gsm_029
and gsm_039 both had faithful translations and still failed for
reasons unrelated to wording).

Then run this script. It diffs your current draft against the
IMMUTABLE original snapshot (*_v1_original.json, written once, never
touched again) to report which tasks you approved verbatim vs edited,
then copies the draft into the real field (content.pt / turns_pt) —
the one pt_available() actually checks. Safe to run repeatedly as you
work through review in batches; already-promoted, unedited tasks are
just re-copied (a no-op), and newly-edited ones update cleanly.

Usage:
    python scripts/promote_pt.py            # promote everything reviewed
    python scripts/promote_pt.py --dry-run  # preview only, write nothing
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
STAGING = ROOT / "prism/suite/w2_staging"


def promote_gsm8k(dry_run: bool):
    draft = json.loads((STAGING / "gsm8k_pt_draft.json").read_text())
    original = json.loads((STAGING / "gsm8k_pt_draft_v1_original.json").read_text())
    real_path = STAGING / "gsm8k_extracted.json"
    real = json.loads(real_path.read_text())
    orig_by_id = {t["id"]: t["content"]["pt_draft"] for t in original["tasks"]}
    real_by_id = {t["id"]: t for t in real["tasks"]}

    verbatim, edited, promoted = 0, 0, 0
    for t in draft["tasks"]:
        cur = t["content"].get("pt_draft")
        if cur is None:
            print(f"  SKIP {t['id']}: no draft to promote")
            continue
        if cur == orig_by_id.get(t["id"]):
            verbatim += 1
        else:
            edited += 1
        real_by_id[t["id"]]["content"]["pt"] = cur
        promoted += 1

    print(f"gsm8k: {promoted}/{len(draft['tasks'])} promoted "
          f"({verbatim} verbatim, {edited} edited)")
    if not dry_run:
        real_path.write_text(json.dumps(real, ensure_ascii=False, indent=1))
    return promoted, verbatim, edited


def promote_bfcl(dry_run: bool):
    draft = json.loads((STAGING / "bfcl_pt_draft.json").read_text())
    original = json.loads((STAGING / "bfcl_pt_draft_v1_original.json").read_text())
    real_path = STAGING / "bfcl_extracted.json"
    real = json.loads(real_path.read_text())
    orig_by_id = {t["id"]: t["turns_pt_draft"] for t in original["tasks"]}
    real_by_id = {t["id"]: t for t in real["tasks"]}

    verbatim, edited, promoted = 0, 0, 0
    for t in draft["tasks"]:
        cur = t.get("turns_pt_draft")
        if not cur or any(x is None for x in cur):
            print(f"  SKIP {t['id']}: draft incomplete")
            continue
        if cur == orig_by_id.get(t["id"]):
            verbatim += 1
        else:
            edited += 1
        real_by_id[t["id"]]["turns_pt"] = cur
        promoted += 1

    print(f"bfcl:  {promoted}/{len(draft['tasks'])} promoted "
          f"({verbatim} verbatim, {edited} edited)")
    if not dry_run:
        real_path.write_text(json.dumps(real, ensure_ascii=False, indent=1))
    return promoted, verbatim, edited


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="Report what would be promoted, write nothing.")
    args = ap.parse_args()

    g_n, g_v, g_e = promote_gsm8k(args.dry_run)
    b_n, b_v, b_e = promote_bfcl(args.dry_run)

    total, verbatim, edited = g_n + b_n, g_v + b_v, g_e + b_e
    print(f"\nTOTAL: {total}/53 promoted"
          + (" (DRY RUN — nothing written)" if args.dry_run else ""))
    if total:
        print(f"  {verbatim} approved verbatim, {edited} required "
              f"human correction ({100*edited/total:.0f}% edit rate) "
              f"— a real statistic for the eventual write-up.")
    if total < 53 and not args.dry_run:
        print(f"  {53 - total} task(s) not yet promoted — rerun after "
              f"reviewing the rest.")


if __name__ == "__main__":
    main()
