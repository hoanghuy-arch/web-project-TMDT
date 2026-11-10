"""Truy vấn dùng cho khu vực nhân viên: bảng điều khiển, danh sách đơn, chi tiết đơn."""
from datetime import timedelta

from flask import abort, current_app
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload

from app.constants import EntityStatus, OrderStatus
from app.extensions import db
from app.models import (Account, AuditLog, ProductVariant, SalesOrder, SalesOrderItem, SalesOrderStatusHistory,
                        Shipment)
from app.models.base import utcnow
from app.services import catalog_service

_VN = timedelta(hours=7)


def status_counts():
    rows = db.session.execute(select(SalesOrder.status, func.count(SalesOrder.id)).group_by(SalesOrder.status)).all()
    return {status: n for status, n in rows}


def orders_today():
    """Số đơn tạo trong ngày hôm nay (tính theo giờ Việt Nam)."""
    local_now = utcnow() + _VN
    start_utc = local_now.replace(hour=0, minute=0, second=0, microsecond=0) - _VN
    return db.session.scalar(select(func.count(SalesOrder.id)).where(SalesOrder.created_at >= start_utc)) or 0


def low_stock_count():
    threshold = catalog_service.low_stock_threshold()
    return db.session.scalar(
        select(func.count(ProductVariant.id)).where(
            ProductVariant.status == EntityStatus.ACTIVE,
            ProductVariant.stock_quantity - ProductVariant.reserved_quantity <= threshold)) or 0


def dashboard_stats():
    return {"counts": status_counts(), "today": orders_today(), "low_stock": low_stock_count(),
            "low_stock_threshold": catalog_service.low_stock_threshold()}


def search_orders(status=None, q="", page=1):
    stmt = (select(SalesOrder)
            .options(selectinload(SalesOrder.account), selectinload(SalesOrder.items), selectinload(SalesOrder.payments))
            .order_by(SalesOrder.created_at.desc(), SalesOrder.id.desc()))
    if status in OrderStatus.ALL:
        stmt = stmt.where(SalesOrder.status == status)
    q = (q or "").strip()[:100]
    if q:
        stmt = stmt.join(Account, Account.id == SalesOrder.account_id).where(or_(
            SalesOrder.order_code.contains(q.upper(), autoescape=True),
            Account.email.contains(q, autoescape=True),
            Account.phone.contains(q, autoescape=True),
            Account.full_name.contains(q, autoescape=True)))
    return db.paginate(stmt, page=page, per_page=current_app.config["ADMIN_ITEMS_PER_PAGE"], error_out=False)


def get_order(order_code):
    order = db.session.scalar(
        select(SalesOrder).where(SalesOrder.order_code == order_code)
        .options(selectinload(SalesOrder.account),
                 selectinload(SalesOrder.items).selectinload(SalesOrderItem.variant).selectinload(ProductVariant.product),
                 selectinload(SalesOrder.items).selectinload(SalesOrderItem.variant).selectinload(ProductVariant.size),
                 selectinload(SalesOrder.items).selectinload(SalesOrderItem.variant).selectinload(ProductVariant.color),
                 selectinload(SalesOrder.status_history).selectinload(SalesOrderStatusHistory.changed_by),
                 selectinload(SalesOrder.payments),
                 selectinload(SalesOrder.shipment).selectinload(Shipment.carrier)))
    if order is None:
        abort(404)
    return order


def incidents(order):
    """Các sự cố giao hàng đã ghi nhận cho đơn (mới nhất trước)."""
    return db.session.scalars(
        select(AuditLog).where(AuditLog.action == "shipment.incident", AuditLog.entity_name == "sales_order",
                               AuditLog.entity_id == order.id)
        .options(selectinload(AuditLog.account)).order_by(AuditLog.id.desc())).all()
