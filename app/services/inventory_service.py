"""Giữ hàng và nhả hàng cho đơn (BR04, BR24). Số dư kho nằm ở product_variant, mọi biến động ghi vào stock_transaction.

Chống bán vượt khi đặt đồng thời: mỗi lần giữ hàng là MỘT câu UPDATE có điều kiện
  UPDATE product_variant SET reserved_quantity = reserved_quantity + :n
  WHERE id = :id AND stock_quantity - reserved_quantity >= :n
Câu lệnh này nguyên tử và tự khóa dòng trên mọi CSDL (MySQL InnoDB, SQLite); số dòng bị ảnh hưởng = 0 nghĩa là
đã hết hàng. Các biến thể luôn được xử lý theo thứ tự id tăng dần để tránh deadlock giữa hai đơn.
CHECK (reserved <= stock, không âm) ở tầng DB là chốt chặn cuối cùng."""
from sqlalchemy import update

from app.constants import StockTxType
from app.extensions import db
from app.models import ProductVariant, StockTransaction
from app.services.errors import InventoryError, StockShortageError


def reserve_for_order(order, actor=None):
    """Giữ hàng cho mọi dòng của đơn. Ném StockShortageError nếu thiếu (người gọi phải rollback)."""
    for item in sorted(order.items, key=lambda i: i.product_variant_id):
        result = db.session.execute(
            update(ProductVariant)
            .where(ProductVariant.id == item.product_variant_id,
                   ProductVariant.stock_quantity - ProductVariant.reserved_quantity >= item.quantity)
            .values(reserved_quantity=ProductVariant.reserved_quantity + item.quantity)
            .execution_options(synchronize_session=False))
        if result.rowcount != 1:
            variant = db.session.get(ProductVariant, item.product_variant_id)
            db.session.refresh(variant)
            available = max(variant.available_quantity, 0)
            raise StockShortageError(
                f"{variant.display_name}: chỉ còn {available} sản phẩm, không đủ số lượng bạn cần ({item.quantity}).")
        db.session.add(StockTransaction(
            product_variant_id=item.product_variant_id, sales_order_id=order.id,
            created_by_account_id=actor.id if actor else None, transaction_type=StockTxType.RESERVE,
            stock_delta=0, reserved_delta=item.quantity, note="Giữ hàng khi tạo đơn"))


def release_for_order(order, actor=None, note="Nhả hàng giữ"):
    """Nhả lượng đã giữ khi đơn bị hủy. Chỉ gọi MỘT lần cho mỗi đơn (được bảo đảm bởi chuyển trạng thái nguyên tử)."""
    for item in sorted(order.items, key=lambda i: i.product_variant_id):
        result = db.session.execute(
            update(ProductVariant)
            .where(ProductVariant.id == item.product_variant_id,
                   ProductVariant.reserved_quantity >= item.quantity)
            .values(reserved_quantity=ProductVariant.reserved_quantity - item.quantity)
            .execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise InventoryError(
                f"Số lượng giữ của biến thể {item.product_variant_id} nhỏ hơn số cần nhả ({item.quantity}) "
                f"khi hủy đơn {order.order_code}")
        db.session.add(StockTransaction(
            product_variant_id=item.product_variant_id, sales_order_id=order.id,
            created_by_account_id=actor.id if actor else None, transaction_type=StockTxType.RELEASE,
            stock_delta=0, reserved_delta=-item.quantity, note=note))


def issue_for_order(order, actor=None, note="Xuất kho khi bàn giao vận chuyển"):
    """Bàn giao vận chuyển: giảm tồn kho và giải phóng đúng lượng đã giữ (stock -n, reserved -n).
    Điều kiện reserved >= n và stock >= n nằm trong chính câu UPDATE; không thỏa thì dừng và rollback toàn bộ."""
    for item in sorted(order.items, key=lambda i: i.product_variant_id):
        result = db.session.execute(
            update(ProductVariant)
            .where(ProductVariant.id == item.product_variant_id,
                   ProductVariant.reserved_quantity >= item.quantity,
                   ProductVariant.stock_quantity >= item.quantity)
            .values(stock_quantity=ProductVariant.stock_quantity - item.quantity,
                    reserved_quantity=ProductVariant.reserved_quantity - item.quantity)
            .execution_options(synchronize_session=False))
        if result.rowcount != 1:
            raise InventoryError(
                f"Không xuất kho được biến thể {item.product_variant_id} cho đơn {order.order_code}: "
                f"lượng giữ hoặc tồn kho nhỏ hơn số lượng cần xuất ({item.quantity})")
        db.session.add(StockTransaction(
            product_variant_id=item.product_variant_id, sales_order_id=order.id,
            created_by_account_id=actor.id if actor else None, transaction_type=StockTxType.ISSUE,
            stock_delta=-item.quantity, reserved_delta=-item.quantity, note=note))


# ------------------------------------------------------------------ cộng/trừ tồn kho theo nguồn
def _change_stock(variant_id, delta, tx_type, actor, note, **source):
    """Đổi stock_quantity một lượng delta (âm hoặc dương) và ghi sổ kho. Không bao giờ để tồn kho nhỏ hơn
    lượng đang giữ (điều kiện nằm trong chính câu UPDATE; CHECK của DB là chốt chặn cuối)."""
    result = db.session.execute(
        update(ProductVariant)
        .where(ProductVariant.id == variant_id,
               ProductVariant.stock_quantity + delta >= ProductVariant.reserved_quantity,
               ProductVariant.stock_quantity + delta >= 0)
        .values(stock_quantity=ProductVariant.stock_quantity + delta)
        .execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise InventoryError("Tồn kho sau điều chỉnh sẽ nhỏ hơn số lượng đang được giữ cho các đơn hàng.")
    db.session.add(StockTransaction(
        product_variant_id=variant_id, created_by_account_id=actor.id if actor else None,
        transaction_type=tx_type, stock_delta=delta, reserved_delta=0, note=note, **source))


def receive_receipt_item(receipt_item, quantity, actor):
    """Nhập kho theo phiếu nhập: chỉ số lượng THỰC NHẬN được cộng vào tồn kho."""
    _change_stock(receipt_item.product_variant_id, quantity, StockTxType.RECEIPT, actor,
                  f"Nhập kho theo phiếu {receipt_item.receipt.receipt_code}", stock_receipt_item_id=receipt_item.id)


def receive_return_item(return_item, quantity, actor):
    """Hàng đổi trả đã nhận và kiểm tra đủ điều kiện bán lại thì cộng lại tồn kho."""
    _change_stock(return_item.order_item.product_variant_id, quantity, StockTxType.RETURN_IN, actor,
                  f"Nhập lại hàng đổi trả #{return_item.return_request_id}", return_item_id=return_item.id)


def adjust_stock(variant_id, delta, actor, reason):
    """Điều chỉnh thủ công (kiểm kê, hàng hỏng/mất...), bắt buộc có lý do."""
    _change_stock(variant_id, delta, StockTxType.ADJUST, actor, reason)
