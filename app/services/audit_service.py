"""Ghi nhật ký thao tác nhạy cảm (FR-HT04). Chỉ thêm vào phiên hiện tại; người gọi tự commit cùng transaction
nghiệp vụ để nhật ký và dữ liệu luôn khớp nhau."""
from flask import has_request_context, request

from app.extensions import db
from app.models import AuditLog


def record(action, entity_name, entity_id, old_value=None, new_value=None, actor=None):
    ip = (request.remote_addr or "unknown") if has_request_context() else "system"
    entry = AuditLog(account_id=actor.id if actor else None, action=action, entity_name=entity_name,
                     entity_id=entity_id, old_value=old_value, new_value=new_value, ip_address=ip)
    db.session.add(entry)
    return entry
