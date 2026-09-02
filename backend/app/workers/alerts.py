"""Background alert-threshold checker. Moved verbatim from main.py (Phase 2A,
no behavior change)."""
import asyncio

from ..database import SessionLocal
from ..models import AlertRuleDB, UserDB
from ..services import market_data
from ..services.telegram import send_telegram_message


async def proactive_price_checker():
    while True:
        await asyncio.sleep(60)
        db = SessionLocal()
        try:
            active_alerts = db.query(AlertRuleDB).filter(AlertRuleDB.alert_triggered == 0).all()
            if not active_alerts: continue

            for item in active_alerts:
                try:
                    query_symbol = f"{item.symbol.upper()}.NS" if not item.symbol.upper().endswith('.NS') else item.symbol.upper()
                    price_info = market_data.get_info(query_symbol)
                    price = price_info.get('currentPrice', price_info.get('regularMarketPrice', 0))
                    if price == 0: continue

                    user = db.query(UserDB).filter(UserDB.id == item.user_id).first()
                    alert_msg = None

                    if item.upper_threshold and price >= item.upper_threshold:
                        alert_msg = f"🚀 *TARGET HIT: {item.symbol}* 🚀\nUser: {user.username}\nPrice crossed above your ₹{item.upper_threshold} target!\n*Current Price: ₹{price}*"
                    elif item.lower_threshold and price <= item.lower_threshold:
                        alert_msg = f"📉 *STOP LOSS ALERT: {item.symbol}* 📉\nUser: {user.username}\nPrice dropped below your ₹{item.lower_threshold} target!\n*Current Price: ₹{price}*"

                    if alert_msg:
                        send_telegram_message(alert_msg)
                        item.alert_triggered = 1
                        db.commit()
                except Exception as e:
                    print(f"Error checking {item.symbol}: {e}")
        finally:
            db.close()
