"""AI Safety Copilot: control-room and tourist-facing chat endpoints. See
services/copilot.py for the intent router these call into."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import require_admin_or_responder, require_self_or_admin
from app.db.session import get_db
from app.models.tourist import Tourist
from app.models.user import User
from app.schemas.copilot import CopilotAnswer, CopilotQuestion
from app.services import copilot
from app.services.safety_card import EMERGENCY_NUMBERS

router = APIRouter(tags=["copilot"])


@router.post("/copilot/ask", response_model=CopilotAnswer)
def ask_operator_copilot(payload: CopilotQuestion, db: Session = Depends(get_db),
                         _: User = Depends(require_admin_or_responder)):
    history = [(h.role, h.text) for h in payload.history]
    return copilot.answer_operator_question(db, payload.question, history=history)


@router.post("/tourists/{tourist_id}/copilot/ask", response_model=CopilotAnswer)
def ask_tourist_copilot(tourist_id: int, payload: CopilotQuestion, db: Session = Depends(get_db),
                        _: User = Depends(require_self_or_admin)):
    t = db.get(Tourist, tourist_id)
    if not t:
        raise HTTPException(status_code=404, detail="Tourist not found")
    history = [(h.role, h.text) for h in payload.history]
    return copilot.answer_tourist_question(db, t, payload.question, history=history)


@router.post("/copilot/public", response_model=CopilotAnswer)
def ask_public_copilot(payload: CopilotQuestion):
    """Pre-login voice assistant (Login/Register screens) -- intentionally
    the only copilot route with no auth dependency, and the only one backed
    by a handler that never touches the database. See
    services/copilot.py::answer_public_question for what that guarantees."""
    return copilot.answer_public_question(payload.question)


@router.get("/copilot/public/emergency-numbers")
def get_public_emergency_numbers():
    """The same real, static national emergency numbers the authenticated
    Safety Card uses (services/safety_card.py) -- reused here, not
    reauthored, so the pre-login voice assistant can speak them (see
    LoginVoiceAssistant.jsx) without a locale file ever hardcoding a number
    that a bad translation could get wrong."""
    return EMERGENCY_NUMBERS
