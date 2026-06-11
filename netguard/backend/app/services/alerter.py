import smtplib
import requests
from email.mime.text import MIMEText
from typing import Optional
from datetime import datetime
from app.config import config
from app.database import SessionLocal
from app.models.alert import Alert

class AlertService:
    def __init__(self):
        self.config = config["alerter"]

    def create_alert(self, device_id: int, alert_type: str, severity: str, message: str) -> Alert:
        db = SessionLocal()
        try:
            alert = Alert(
                device_id=device_id,
                alert_type=alert_type,
                severity=severity,
                message=message
            )
            db.add(alert)
            db.commit()
            db.refresh(alert)
            self._send_notifications(alert)
            return alert
        finally:
            db.close()

    def _send_notifications(self, alert: Alert):
        if self.config["email"]["enabled"]:
            self._send_email(alert)
        if self.config["wechat"]["enabled"]:
            self._send_wechat(alert)
        if self.config["dingtalk"]["enabled"]:
            self._send_dingtalk(alert)

    def _send_email(self, alert: Alert):
        email_config = self.config["email"]
        msg = MIMEText(f"NetGuard Alert: {alert.message}")
        msg["Subject"] = f"[NetGuard] {alert.severity}: {alert.alert_type}"
        msg["From"] = email_config["username"]
        msg["To"] = email_config["username"]
        try:
            with smtplib.SMTP(email_config["smtp_server"], email_config["smtp_port"]) as server:
                server.starttls()
                server.login(email_config["username"], email_config["password"])
                server.send_message(msg)
        except Exception as e:
            print(f"Email alert failed: {e}")

    def _send_wechat(self, alert: Alert):
        wechat_config = self.config["wechat"]
        payload = {
            "msgtype": "text",
            "text": {"content": f"NetGuard Alert: {alert.severity}\n{alert.message}"}
        }
        try:
            requests.post(wechat_config["webhook_url"], json=payload, timeout=10)
        except Exception as e:
            print(f"WeChat alert failed: {e}")

    def _send_dingtalk(self, alert: Alert):
        dingtalk_config = self.config["dingtalk"]
        payload = {
            "msgtype": "text",
            "text": {"content": f"NetGuard Alert: {alert.severity}\n{alert.message}"}
        }
        try:
            requests.post(dingtalk_config["webhook_url"], json=payload, timeout=10)
        except Exception as e:
            print(f"DingTalk alert failed: {e}")

    def acknowledge_alert(self, alert_id: int, user: str) -> bool:
        db = SessionLocal()
        try:
            alert = db.query(Alert).filter(Alert.id == alert_id).first()
            if alert:
                alert.acknowledged = True
                alert.acknowledged_by = user
                alert.acknowledged_at = datetime.now()
                db.commit()
                return True
            return False
        finally:
            db.close()
