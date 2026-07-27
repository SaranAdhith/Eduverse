"""Graph module model re-exports (DOC_02 §4).

The ORM tables live in :mod:`app.modules.topics.model`; the graph module owns no
new tables, so it simply re-exports them for convenience.
"""
from app.modules.topics.model import Topic, TopicPrerequisite

__all__ = ["Topic", "TopicPrerequisite"]
