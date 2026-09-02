from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import AlertRuleDB, UserDB
from ..security import get_current_user
from ..services.telegram import send_telegram_message

router = APIRouter()


class AlertData(BaseModel):
    symbol: str
    current_price: float
    open: float
    high: float
    low: float
    previous_close: float
    suggestion: str
    percent_change: float
    volume: int
    prediction: dict | None = None


class AlertCreate(BaseModel):
    symbol: str
    upper_threshold: float | None = None
    lower_threshold: float | None = None
    group_id: int | None = None


class AlertItemOut(BaseModel):
    model_config = {"from_attributes": True}
    id: int
    symbol: str
    upper_threshold: float | None
    lower_threshold: float | None
    alert_triggered: int
    group_id: int | None


@router.post("/api/telegram/alert")
def send_telegram_alert(data: AlertData, current_user: UserDB = Depends(get_current_user)):
    trend_emoji = "🚀" if data.percent_change >= 0 else "📉"
    prediction_text = ""

    if data.prediction:
        active_algo = data.prediction.get("active", "INTRADAY").lower()
        active_prediction = data.prediction.get(active_algo, {})
        prediction_text = (
            f"\n\n*Active Algo:* {data.prediction.get('active', 'INTRADAY')}\n"
            f"*Prediction:* *{active_prediction.get('direction', 'N/A')}* "
            f"({active_prediction.get('rise_probability', 50)}% rise / "
            f"{active_prediction.get('fall_probability', 50)}% fall)\n"
            f"*Target:* Rs. {active_prediction.get('target_price', data.current_price)} | "
            f"*Confidence:* {active_prediction.get('confidence', 'Low')}"
        )

    message = (
        f"🚨 *PRO ALGO ALERT* 🚨\n\n"
        f"👤 *Trader:* {current_user.username}\n"
        f"📈 *Stock:* {data.symbol}\n"
        f"💵 *Price:* ₹{data.current_price} ({trend_emoji} {data.percent_change}%)\n"
        f"📊 *Volume:* {data.volume:,}\n\n"
        f"🎯 *Day High:* ₹{data.high} | 🔻 *Day Low:* ₹{data.low}\n\n"
        f"🤖 *Algo Signal:* *{data.suggestion}*"
        f"{prediction_text}"
    )

    send_telegram_message(message)
    return {"message": "Rich alert sent to Telegram!"}


# --- ALERTS (threshold-based price alerting) ---
@router.get("/api/alerts", response_model=list[AlertItemOut])
def get_alerts(current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(AlertRuleDB).filter(AlertRuleDB.user_id == current_user.id).all()


@router.post("/api/alerts", response_model=AlertItemOut)
def add_alert(item: AlertCreate, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    new_item = AlertRuleDB(
        user_id=current_user.id, symbol=item.symbol.upper(),
        upper_threshold=item.upper_threshold, lower_threshold=item.lower_threshold,
        group_id=item.group_id,
    )
    db.add(new_item)
    db.commit()
    db.refresh(new_item)
    return new_item


@router.delete("/api/alerts/{item_id}")
def delete_alert(item_id: int, current_user: UserDB = Depends(get_current_user), db: Session = Depends(get_db)):
    item = db.query(AlertRuleDB).filter(AlertRuleDB.id == item_id, AlertRuleDB.user_id == current_user.id).first()
    if item:
        db.delete(item)
        db.commit()
    return {"message": "Deleted"}
