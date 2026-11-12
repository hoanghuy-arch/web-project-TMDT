"""Tồn kho và phiếu nhập (FR-NV06, FR-NV07, FR-QT05). Một kho duy nhất; mọi biến động ghi vào stock_transaction.
Phiếu nhập: DRAFT -> CONFIRMED (chỉ số lượng THỰC NHẬN được cộng vào tồn kho) hoặc DRAFT -> CANCELLED."""
from decimal import Decimal

from flask import abort, current_app
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.constants import EntityStatus, ReceiptStatus
from app.extensions import db
from app.models import (Product, ProductVariant, StockReceipt, StockReceiptItem, StockTransaction, Supplier)
from app.models.base import utcnow
from app.services import audit_service, catalog_service, inventory_service
from app.services.errors import ConcurrentUpdateError, InventoryError, StockError
from app.utils.codes import generate_receipt_code

MAX_QTY = 1_000_000
MAX_RECEIPT_LINES = 50


# ================================================================== xem tồn kho
def search_variants(q="", low_only=False, page=1):
    available = ProductVariant.stock_quantity - ProductVariant.reserved_quantity
    stmt = (select(ProductVariant).join(Product, Product.id == ProductVariant.product_id)
            .options(selectinload(ProductVariant.product), selectinload(ProductVariant.size),
                     selectinload(ProductVariant.color))
            .order_by(available.asc(), ProductVariant.id))
    q = (q or "").strip()[:100]
    if q:
        stmt = stmt.where(or_(Product.name.contains(q, autoescape=True), ProductVariant.sku.contains(q, autoescape=True)))
    if low_only:
        stmt = stmt.where(ProductVariant.status == EntityStatus.ACTIVE,
                          available <= catalog_service.low_stock_threshold())
    return db.paginate(stmt, page=page, per_page=current_app.config["ADMIN_ITEMS_PER_PAGE"], error_out=False)


def get_variant(variant_id):
    variant = db.session.scalar(select(ProductVariant).where(ProductVariant.id == variant_id)
                                .options(selectinload(ProductVariant.product), selectinload(ProductVariant.size),
                                         selectinload(ProductVariant.color)))
    if variant is None:
        abort(404)
    return variant


def recent_transactions(variant, limit=40):
    return db.session.scalars(
        select(StockTransaction).where(StockTransaction.product_variant_id == variant.id)
        .options(selectinload(StockTransaction.created_by))
        .order_by(StockTransaction.id.desc()).limit(limit)).all()


def adjust(variant, actor, delta, reason):
    """Điều chỉnh tồn kho thủ công (cộng/trừ), bắt buộc có lý do; không cho tồn nhỏ hơn lượng đang giữ."""
    reason = (reason or "").strip()
    if delta is None or delta == 0 or abs(delta) > MAX_QTY:
        raise StockError("Số lượng điều chỉnh phải khác 0 (dùng số âm để giảm tồn kho).")
    if len(reason) < 5:
        raise StockError("Vui lòng nhập lý do điều chỉnh (ít nhất 5 ký tự).")
    old_stock = variant.stock_quantity
    try:
        inventory_service.adjust_stock(variant.id, delta, actor, reason[:500])
        audit_service.record("stock.adjust", "product_variant", variant.id,
                             {"stock_quantity": old_stock}, {"stock_quantity": old_stock + delta, "reason": reason[:500]}, actor)
        db.session.commit()
    except InventoryError:
        db.session.rollback()
        raise StockError("Không thể giảm tồn kho xuống thấp hơn số lượng đang được giữ cho các đơn hàng chưa bàn giao.")
    except Exception:
        db.session.rollback()
        raise


# ================================================================== phiếu nhập
def active_suppliers():
    return db.session.scalars(select(Supplier).where(Supplier.status == EntityStatus.ACTIVE).order_by(Supplier.name)).all()


def _parse_lines(lines):
    """lines: [(sku, ordered_qty, unit_cost)] -> [(variant, ordered_qty, unit_cost)] đã kiểm tra."""
    cleaned = [(sku.strip(), qty, cost) for sku, qty, cost in lines if (sku or "").strip()]
    if not cleaned:
        raise StockError("Phiếu nhập cần có ít nhất một dòng hàng.")
    if len(cleaned) > MAX_RECEIPT_LINES:
        raise StockError(f"Mỗi phiếu nhập tối đa {MAX_RECEIPT_LINES} dòng.")
    result, seen = [], set()
    for sku, qty, cost in cleaned:
        variant = db.session.scalar(select(ProductVariant).where(func.upper(ProductVariant.sku) == sku.upper()))
        if variant is None:
            raise StockError(f"Không tìm thấy mã SKU \"{sku}\".")
        if variant.id in seen:
            raise StockError(f"SKU \"{variant.sku}\" bị lặp trong phiếu nhập.")
        seen.add(variant.id)
        if qty is None or not 1 <= qty <= MAX_QTY:
            raise StockError(f"Số lượng đặt nhập của {variant.sku} phải từ 1 đến {MAX_QTY:,}.".replace(",", "."))
        if cost is None or cost < 0 or cost > 1_000_000_000:
            raise StockError(f"Đơn giá nhập của {variant.sku} không hợp lệ.")
        result.append((variant, qty, cost))
    return result


def create_receipt(actor, supplier_id, note, lines):
    supplier = db.session.get(Supplier, supplier_id) if supplier_id else None
    if supplier is None or supplier.status != EntityStatus.ACTIVE:
        raise StockError("Vui lòng chọn nhà cung cấp hợp lệ.")
    parsed = _parse_lines(lines)
    for _ in range(10):
        code = generate_receipt_code(utcnow())
        if not db.session.scalar(select(StockReceipt.id).where(StockReceipt.receipt_code == code)):
            break
    else:
        raise RuntimeError("Không sinh được mã phiếu nhập duy nhất")
    receipt = StockReceipt(receipt_code=code, supplier_id=supplier.id, created_by_account_id=actor.id,
                           status=ReceiptStatus.DRAFT, note=(note or "").strip()[:500] or None)
    for variant, qty, cost in parsed:
        receipt.items.append(StockReceiptItem(product_variant_id=variant.id, ordered_quantity=qty,
                                              received_quantity=0, unit_cost=Decimal(cost)))
    db.session.add(receipt)
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        raise StockError("Không lưu được phiếu nhập, vui lòng thử lại.")
    return receipt


def _claim(receipt, to_status, values=None):
    result = db.session.execute(
        update(StockReceipt).where(StockReceipt.id == receipt.id, StockReceipt.status == ReceiptStatus.DRAFT)
        .values(status=to_status, **(values or {})).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise ConcurrentUpdateError("Phiếu nhập đã được xử lý trước đó.")
    db.session.expire(receipt)


def confirm_receipt(receipt, actor, received):
    """received: {stock_receipt_item_id: số lượng thực nhận}. Chỉ phần thực nhận được cộng vào tồn kho."""
    if receipt.status != ReceiptStatus.DRAFT:
        raise StockError("Phiếu nhập này đã được xử lý.")
    plan = {}
    for item in receipt.items:
        qty = received.get(item.id)
        if qty is None or qty < 0 or qty > MAX_QTY:
            raise StockError(f"Số lượng thực nhận của {item.variant.sku} không hợp lệ.")
        plan[item.id] = qty
    if not any(plan.values()):
        raise StockError("Chưa có số lượng thực nhận nào. Nếu không nhận được hàng, hãy hủy phiếu nhập.")
    try:
        _claim(receipt, ReceiptStatus.CONFIRMED, {"confirmed_at": utcnow()})
        for item in receipt.items:
            item.received_quantity = plan[item.id]
            if plan[item.id] > 0:
                inventory_service.receive_receipt_item(item, plan[item.id], actor)
        audit_service.record("stock.receipt_confirm", "stock_receipt", receipt.id, {"status": ReceiptStatus.DRAFT},
                             {"status": ReceiptStatus.CONFIRMED, "received": {i.variant.sku: plan[i.id] for i in receipt.items}}, actor)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return receipt


def cancel_receipt(receipt, actor):
    if receipt.status != ReceiptStatus.DRAFT:
        raise StockError("Chỉ hủy được phiếu nhập đang ở trạng thái nháp.")
    try:
        _claim(receipt, ReceiptStatus.CANCELLED)
        audit_service.record("stock.receipt_cancel", "stock_receipt", receipt.id, {"status": ReceiptStatus.DRAFT},
                             {"status": ReceiptStatus.CANCELLED}, actor)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return receipt


def list_receipts(status=None, page=1):
    stmt = (select(StockReceipt).options(selectinload(StockReceipt.supplier), selectinload(StockReceipt.items),
                                         selectinload(StockReceipt.created_by))
            .order_by(StockReceipt.created_at.desc(), StockReceipt.id.desc()))
    if status in ReceiptStatus.ALL:
        stmt = stmt.where(StockReceipt.status == status)
    return db.paginate(stmt, page=page, per_page=current_app.config["ADMIN_ITEMS_PER_PAGE"], error_out=False)


def get_receipt(receipt_id):
    receipt = db.session.scalar(
        select(StockReceipt).where(StockReceipt.id == receipt_id)
        .options(selectinload(StockReceipt.supplier), selectinload(StockReceipt.created_by),
                 selectinload(StockReceipt.items).selectinload(StockReceiptItem.variant).selectinload(ProductVariant.product),
                 selectinload(StockReceipt.items).selectinload(StockReceiptItem.variant).selectinload(ProductVariant.size),
                 selectinload(StockReceipt.items).selectinload(StockReceiptItem.variant).selectinload(ProductVariant.color)))
    if receipt is None:
        abort(404)
    return receipt
