"""Multi-agent feature improvement system for March Madness predictor.

Four agents collaborate in a loop to iteratively improve feature quality:

1. Supervisor - orchestrates the loop, accepts/rejects proposals
2. Reviewer - analyzes feature quality and identifies gaps
3. Basketball Analyst - domain-informed feature suggestions
4. Feature Agent - implements code changes

Usage:
    python scripts/run_agents.py --max-iterations 5
"""
