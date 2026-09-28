"""Currency conversion API. See services/currency.py."""
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_current_user
from app.models.user import User
from app.services import currency

router = APIRouter(prefix="/currency", tags=["currency"])


@router.get("/list")
def list_currencies(_: User = Depends(get_current_user)):
    return currency.list_currencies()


@router.get("/convert")
def convert(
    amount: float = Query(..., gt=0, le=10_000_000),
    to: str = Query(..., min_length=3, max_length=3),
    _: User = Depends(get_current_user),
):
    return currency.convert_from_inr(amount, to)
