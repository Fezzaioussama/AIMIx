"""Approval gates: inside a run, a tool that can change an outside system waits
for the run owner's OK before it acts (docs/architecture.md, "Approval gates").

``policy`` decides which tools ask first, ``gate`` records a request and waits
for the answer, ``middleware`` puts the gate in front of each such tool call,
``guard`` hands an agent its tools accordingly, and ``decisions`` takes the
owner's answer.
"""
