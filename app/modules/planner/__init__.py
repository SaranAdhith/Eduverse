"""Path planner & mastery gate (DOC_05).

Decides what topic a participant studies next, in what order, and gates each
step behind real BKT mastery. Introduces the study's ``mode`` flag:
``personalized`` (BKT + graph + Claude) vs ``fixed`` (deterministic topological
traversal). Every other component is identical across modes — that is what makes
the study comparison clean.
"""
