"""Cultural Etiquette Guide API. See services/etiquette.py."""
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User
from app.services import etiquette

router = APIRouter(prefix="/etiquette", tags=["etiquette"])


@router.get("/topics")
def list_topics(_: User = Depends(get_current_user)):
    return etiquette.list_topics()


@router.get("/{topic}")
def get_topic(topic: str, lang: str = Query("en", max_length=10), _: User = Depends(get_current_user)):
    return etiquette.get_topic(topic, lang)
