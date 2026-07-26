# Prism — W1 harness

Verified in CI with the scripted mock (48 attempts, all 8 cells, token-sum
invariants enforced). On the Mac:

    cd ~/Projects/prism
    python3 -m venv .venv && source .venv/bin/activate
    pip install mlx-lm groq

Smoke test (1 task, real model, tokenizer-exact accounting):

    python run_pilot.py --model mlx --limit 1 --seeds 1

Full W1 pilot on M1 (spec gate: harness errors <5%, hardest-cell acc >15%,
power fits n=80):

    python run_pilot.py --model mlx
    python -m prism.analysis.aggregate results/<run>.jsonl --power

Groq validation arm later (needs GROQ_API_KEY exported):

    python run_pilot.py --model groq --limit 2 --seeds 1
