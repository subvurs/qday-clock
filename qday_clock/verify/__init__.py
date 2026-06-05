"""Verification utilities — replay scoring from a signed manifest.

Per CLAUDE.md section 4 (reproducibility) and plan section F, every
shipped clock_state.json must be replayable: given the same inputs
and the same code, re-running the scoring pipeline must produce the
same canonical bytes.
"""
