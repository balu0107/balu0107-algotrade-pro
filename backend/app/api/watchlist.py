from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import StockGroupDB, TrackedStockDB, AlertRuleDB, UserDB
from ..security import get_current_user

router = APIRouter()


class TrackedStockCreate(BaseModel):
    symbol: str
    group_id: int | None = None


class TrackedStockOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    symbol: str
    group_id: int | None


class StockGroupCreate(BaseModel):
    group_type: Literal["watchlist", "alert"]
    name: str


class StockGroupRename(BaseModel):
    name: str


class StockGroupOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    group_type: str
    name: str


MAX_GROUPS_PER_TYPE = 10


# --- PLAIN WATCHLIST (just tracking, no thresholds) ---
@router.get("/api/tracked-stocks", response_model=list[TrackedStockOut])
def get_tracked_stocks(current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(TrackedStockDB).filter(TrackedStockDB.user_id == current_user.id).all()


@router.post("/api/tracked-stocks", response_model=TrackedStockOut)
def add_tracked_stock(item: TrackedStockCreate, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    new_item = TrackedStockDB(user_id=current_user.id, symbol=item.symbol.upper(), group_id=item.group_id)
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


@router.delete("/api/tracked-stocks/{item_id}")
def delete_tracked_stock(item_id: int, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(TrackedStockDB).filter(TrackedStockDB.id == item_id, TrackedStockDB.user_id == current_user.id).first()
    if item:
        db.delete(item)
        db.commit()
    return {"message": "Deleted"}


# --- CUSTOM GROUPS (named folders, shared by Watchlist + Alerts, up to 10 per type) ---
@router.get("/api/groups", response_model=list[StockGroupOut])
def get_groups(group_type: Literal["watchlist", "alert"] = Query(...), current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    return (
        db.query(StockGroupDB)
        .filter(StockGroupDB.user_id == current_user.id, StockGroupDB.group_type == group_type)
        .order_by(StockGroupDB.id)
        .all()
    )


@router.post("/api/groups", response_model=StockGroupOut)
def create_group(payload: StockGroupCreate, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    existing_count = (
        db.query(StockGroupDB)
        .filter(StockGroupDB.user_id == current_user.id, StockGroupDB.group_type == payload.group_type)
        .count()
    )
    if existing_count >= MAX_GROUPS_PER_TYPE:
        raise HTTPException(status_code=400, detail=f"You can only have {MAX_GROUPS_PER_TYPE} groups per type.")
    new_group = StockGroupDB(user_id=current_user.id, group_type=payload.group_type, name=payload.name.strip())
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return new_group


@router.put("/api/groups/{group_id}", response_model=StockGroupOut)
def rename_group(group_id: int, payload: StockGroupRename, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.query(StockGroupDB).filter(StockGroupDB.id == group_id, StockGroupDB.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    group.name = payload.name.strip()
    db.commit()
    db.refresh(group)
    return group


@router.delete("/api/groups/{group_id}")
def delete_group(group_id: int, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    group = db.query(StockGroupDB).filter(StockGroupDB.id == group_id, StockGroupDB.user_id == current_user.id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found.")
    # Members are ungrouped, not deleted - losing a folder shouldn't silently
    # delete the stocks/alerts inside it.
    ungrouped_count = 0
    if group.group_type == "watchlist":
        ungrouped_count = db.query(TrackedStockDB).filter(TrackedStockDB.group_id == group_id).update({"group_id": None})
    else:
        ungrouped_count = db.query(AlertRuleDB).filter(AlertRuleDB.group_id == group_id).update({"group_id": None})
    db.delete(group)
    db.commit()
    return {"message": "Deleted", "ungrouped_count": ungrouped_count}
