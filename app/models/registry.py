"""Model registry: importing this module ensures every ORM model is imported
so that ``Base.metadata`` is complete (for Alembic autogenerate and
``create_all`` in tests). Later phases append their model imports here.
"""
from app.models.base import Base
from app.modules.content.model import ChunkQuizItem, ContentChunk
from app.modules.curation.model import (
    TopicVideoCoverage,
    VideoResource,
    VideoSegment,
)
from app.modules.mastery.model import DiagnosticSession, Mastery, Response
from app.modules.participants.model import Participant
from app.modules.planner.model import GateAttempt, LearningPath, PathStep
from app.modules.questions.model import Choice, Question
from app.modules.study.model import Event, LLMCache, StudyAssignment
from app.modules.topics.model import Topic, TopicPrerequisite

__all__ = [
    "Base",
    "Choice",
    "ChunkQuizItem",
    "ContentChunk",
    "DiagnosticSession",
    "Event",
    "GateAttempt",
    "LLMCache",
    "LearningPath",
    "Mastery",
    "Participant",
    "PathStep",
    "Question",
    "Response",
    "StudyAssignment",
    "Topic",
    "TopicPrerequisite",
    "TopicVideoCoverage",
    "VideoResource",
    "VideoSegment",
]
