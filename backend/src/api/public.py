from fastapi import APIRouter, HTTPException, Query

from ..schemas import TopicDetailResponse, TopicPositionsResponse, TopicsResponse
from ..services.stub_data import scores_by_topic, topics


router = APIRouter()


@router.get("/topics", response_model=TopicsResponse)
def list_topics() -> TopicsResponse:
    return TopicsResponse(topics=topics)


@router.get("/topics/{topic_id}/positions", response_model=TopicPositionsResponse)
def get_topic_positions(
    topic_id: str,
    mode: str = Query("claim", pattern="^(claim|action|combined)$"),
    entity: str = Query("party", pattern="^(party|party\\+politician)$"),
) -> TopicPositionsResponse:
    topic = next((t for t in topics if t.topic_id == topic_id), None)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")

    scores = [s for s in scores_by_topic.get(topic_id, []) if s.mode == mode]
    return TopicPositionsResponse(topic=topic, mode=mode, entity=entity, scores=scores)


@router.get("/entities/{entity_id}/topics/{topic_id}/detail", response_model=TopicDetailResponse)
def get_topic_detail(
    entity_id: str,
    topic_id: str,
    mode: str = Query("claim", pattern="^(claim|action|combined)$"),
) -> TopicDetailResponse:
    topic = next((t for t in topics if t.topic_id == topic_id), None)
    if not topic:
        raise HTTPException(status_code=404, detail="topic not found")

    score = next(
        (s for s in scores_by_topic.get(topic_id, []) if s.entity_id == entity_id and s.mode == mode),
        None,
    )
    if not score:
        raise HTTPException(status_code=404, detail="score not found")

    return TopicDetailResponse(topic=topic, mode=mode, entity_id=entity_id, score=score)
