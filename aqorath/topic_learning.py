"""Pure explicit acknowledgement of locally learned topics."""

from dataclasses import replace
from datetime import datetime

from .user_knowledge_state import LearnedTopic, UserKnowledgeState


def record_learned_topic(user_state, topic, learned_at):
    """Return state with one explicitly acknowledged learned topic."""
    if not isinstance(user_state, UserKnowledgeState):
        raise TypeError("user_state must be UserKnowledgeState")
    if type(topic) is not str:
        raise TypeError("topic must be str")
    if not topic or topic.strip() != topic:
        raise ValueError("topic must be nonblank without surrounding whitespace")
    if type(learned_at) is not datetime:
        raise TypeError("learned_at must be datetime")

    for learned in user_state.learned_topics:
        if learned.topic != topic:
            continue
        if learned.learned_at == learned_at:
            return user_state
        raise ValueError("topic learning already exists with a different timestamp")

    learned = LearnedTopic(topic=topic, learned_at=learned_at)
    return replace(
        user_state,
        learned_topics=user_state.learned_topics + (learned,),
    )
