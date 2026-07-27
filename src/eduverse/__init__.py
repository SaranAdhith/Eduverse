"""Eduverse: an adaptive Python-learning agent (research prototype).

See DOC_00 for the curriculum knowledge graph, diagnostic design, BKT mastery
model, and the crossover study this prototype is built to evaluate.
"""
from .bkt import BKTParams, is_mastered, load_params, posterior, update
from .curriculum import Curriculum, CurriculumError
from .diagnostic import Blueprint
from .models import BlueprintEntry, Tier, Topic

__all__ = [
    "BKTParams",
    "Blueprint",
    "BlueprintEntry",
    "Curriculum",
    "CurriculumError",
    "Tier",
    "Topic",
    "is_mastered",
    "load_params",
    "posterior",
    "update",
]

__version__ = "0.1.0"
