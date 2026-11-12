"""Đặt hàng, hủy đơn, chuyển trạng thái, truy vấn đơn (FR-KH08..12, FR-HT01, FR-HT03).

Nguyên tắc:
- Mọi thao tác ghi (đặt đơn, hủy đơn) nằm trong MỘT transaction: lỗi ở bất kỳ bước nào thì rollback toàn bộ
  (không có đơn "mồ côi", không giữ hàng dở dang).
- Mọi chuyển trạng thái đi qua change_status(): kiểm tra theo sơ đồ trạng thái, cập nhật nguyên tử theo
  trạng thái hiện tại (chống hai người cùng xử lý một đơn) và luôn ghi lịch sử."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from flask import abort, current_app
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.constants import (CUSTOMER_CANCELLABLE_STATUSES, ROLE_CUSTOMER, STAFF_CANCELLABLE_STATUSES,
                           OrderStatus, PaymentMethod, PaymentStatus, can_transition)
from app.extensions import db
from app.models import (Address, AppSetting, Payment, ProductVariant, ReturnRequest, SalesOrder, SalesOrderItem,
                        SalesOrderStatusHistory)
from app.models.base import utcnow
from app.services import (address_service, audit_service, cart_service, inventory_service, promotion_service,
                          shipping_service)
from app.services.cart_view import CartView
from app.services.errors import (CheckoutError, ConcurrentUpdateError, OrderStateError, PromotionError)
from app.utils.codes import generate_order_code, generate_txn_ref


# ================================================================== xem trước đơn (trang checkout)
@dataclass
class CheckoutSummary:
    cart: CartView
    address: Address = None
    promo_code: str = ""
    promotion: object = None
    promo_error: str = None
    discount: Decimal = Decimal(0)
    shipping_fee: Decimal = Decimal(0)
    free_shipping: bool = False

    @property
    def subtotal(self):
        return self.cart.subtotal

    @property
    def total(self):
        return self.subtotal - self.discount + self.shipping_fee


def pick_address(addresses, address_id):
    """Địa chỉ đang chọn: theo id nếu hợp lệ, ngược lại địa chỉ mặc định, ngược lại địa chỉ đầu tiên."""
    by_id = {a.id: a for a in addresses}
    if address_id in by_id:
        return by_id[address_id]
    return next((a for a in addresses if a.is_default), addresses[0] if addresses else None)


def build_checkout(account, address_id=None, promo_code=""):
    """Tính trước tiền hàng, giảm giá, phí vận chuyển để hiển thị. Không ghi gì vào DB, không giữ hàng."""
    cart = cart_service.get_cart(account)
    address = pick_address(address_service.list_active_addresses(account), address_id)
    summary = CheckoutSummary(cart=cart, address=address, promo_code=promotion_service.normalize_code(promo_code))

    if summary.promo_code:
        try:
            summary.promotion, summary.discount = promotion_service.evaluate(summary.promo_code, cart.subtotal)
        except PromotionError as e:
            summary.promo_error = str(e)
    if address is not None:
        q = shipping_service.quote(address.ward.province_id, cart.subtotal)
        summary.shipping_fee, summary.free_shipping = q.fee, q.free
    return summary


# ================================================================== chuyển trạng thái
def change_status(order, to_status, actor=None, reason=None):
    """Chuyển trạng thái hợp lệ + ghi lịch sử. KHÔNG commit (người gọi gộp với các bước khác rồi commit).
    Cập nhật có điều kiện (WHERE status = trạng thái vừa đọc) nên hai thao tác đồng thời không thể cùng thành công."""
    current = db.session.scalar(select(SalesOrder.status).where(SalesOrder.id == order.id))
    if not can_transition(current, to_status):
        raise OrderStateError(
            f"Không thể chuyển đơn từ \"{OrderStatus.LABELS.get(current, current)}\" "
            f"sang \"{OrderStatus.LABELS.get(to_status, to_status)}\".")
    result = db.session.execute(
        update(SalesOrder).where(SalesOrder.id == order.id, SalesOrder.status == current)
        .values(status=to_status, updated_at=utcnow()).execution_options(synchronize_session=False))
    if result.rowcount != 1:
        raise ConcurrentUpdateError("Đơn hàng vừa được cập nhật bởi một thao tác khác. Vui lòng tải lại trang.")
    db.session.add(SalesOrderStatusHistory(
        sales_order_id=order.id, to_status=to_status, reason=reason,
        changed_by_account_id=actor.id if actor else None))
    db.session.flush()
    db.session.expire(order)
    return order


# ================================================================== đặt hàng
def _new_order_code():
    for _ in range(10):
        code = generate_order_code(utcnow())
        if not db.session.scalar(select(SalesOrder.id).where(SalesOrder.order_code == code)):
            return code
    raise RuntimeError("Không sinh được mã đơn duy nhất")


def place_order(account, address_id, promo_code, payment_method, note=None):
    """Tạo đơn từ giỏ hàng, giữ hàng, ghi lịch sử và thanh toán, xóa giỏ, tất cả trong một transaction.
    COD -> chờ xác nhận. Online -> chờ thanh toán (hết hạn sau thời gian giữ hàng cấu hình, mặc định 15 phút)."""
    if payment_method not in PaymentMethod.ALL:
        raise CheckoutError("Phương thức thanh toán không hợp lệ.")

    cart = cart_service.get_cart(account)
    if not cart.lines:
        raise CheckoutError("Giỏ hàng của bạn đang trống.")
    if not cart.can_checkout:
        raise CheckoutError("Có sản phẩm trong giỏ không thể đặt. Vui lòng kiểm tra lại giỏ hàng.")

    address = next((a for a in address_service.list_active_addresses(account) if a.id == address_id), None)
    if address is None:
        raise CheckoutError("Vui lòng chọn địa chỉ nhận hàng hợp lệ.")

    try:
        promotion, discount = None, Decimal(0)
        code = promotion_service.normalize_code(promo_code)
        if code:
            promotion, discount = promotion_service.evaluate(code, cart.subtotal, lock=True)
        quote = shipping_service.quote(address.ward.province_id, cart.subtotal)

        online = payment_method == PaymentMethod.VNPAY
        status = OrderStatus.PENDING_PAYMENT if online else OrderStatus.PENDING_CONFIRM
        order = SalesOrder(
            order_code=_new_order_code(), account_id=account.id, address_id=address.id,
            promotion_id=promotion.id if promotion else None, status=status,
            discount_amount=discount, shipping_fee=quote.fee, note=(note or "").strip()[:500] or None)
        for line in cart.lines:
            # Giá chốt tại thời điểm đặt (BR05)
            order.items.append(SalesOrderItem(product_variant_id=line.variant.id, quantity=line.quantity,
                                              unit_price=line.unit_price))
        db.session.add(order)
        db.session.flush()

        inventory_service.reserve_for_order(order, actor=account)      # ném StockShortageError nếu thiếu hàng

        db.session.add(SalesOrderStatusHistory(sales_order_id=order.id, to_status=status,
                                               changed_by_account_id=account.id, reason="Khách đặt hàng"))
        db.session.add(Payment(
            sales_order_id=order.id, method=payment_method,
            status=PaymentStatus.PENDING if online else PaymentStatus.UNPAID,
            amount=order.total_amount, gateway_txn_ref=generate_txn_ref(order.order_code) if online else None))
        cart_service.clear_cart(account)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    if payment_method == PaymentMethod.COD:         # đơn online gửi email sau khi thanh toán thành công
        notify_order_placed(order)
    return order


def notify_order_placed(order, payment_method=PaymentMethod.COD):
    """Email xác nhận đơn (FR-HT02). Lỗi gửi email không được làm hỏng đơn đã tạo."""
    if payment_method != PaymentMethod.COD:
        return
    try:
        from app.services.email_service import send_order_confirmation_email
        send_order_confirmation_email(order)
    except Exception:       # lỗi email không được làm hỏng đơn đã tạo
        current_app.logger.exception("Gửi email xác nhận đơn %s thất bại", order.order_code)


# ================================================================== hủy đơn
def cancel_order(order, actor=None, reason=None):
    """Hủy đơn, nhả hàng giữ, xử lý thanh toán, ghi lịch sử (và nhật ký với thao tác của nhân viên/hệ thống).
    Ai được hủy:
      - khách hàng (chủ đơn): khi Chờ xác nhận hoặc Đã xác nhận;
      - nhân viên/quản trị viên: khi Chờ xác nhận, Đã xác nhận hoặc Đang đóng gói, BẮT BUỘC có lý do;
      - hệ thống (actor=None): chỉ đơn Chờ thanh toán (thanh toán thất bại hoặc quá hạn)."""
    reason = (reason or "").strip()[:500] or None
    db.session.refresh(order)
    is_customer = actor is not None and actor.role_code == ROLE_CUSTOMER

    if actor is None:
        allowed = (OrderStatus.PENDING_PAYMENT,)
    elif is_customer:
        if order.account_id != actor.id:
            raise OrderStateError("Bạn không có quyền hủy đơn hàng này.")
        allowed = CUSTOMER_CANCELLABLE_STATUSES
    else:
        allowed = STAFF_CANCELLABLE_STATUSES
        if not reason:
            raise OrderStateError("Vui lòng nhập lý do hủy đơn.")
    if order.status not in allowed:
        raise OrderStateError(
            f"Đơn hàng đang ở trạng thái \"{OrderStatus.LABELS[order.status]}\" nên không thể hủy.")

    old_status = order.status
    try:
        change_status(order, OrderStatus.CANCELLED, actor, reason or ("Khách hàng hủy đơn" if is_customer else None))
        inventory_service.release_for_order(order, actor, note=f"Nhả hàng do hủy đơn {order.order_code}")
        _settle_payment_on_cancel(order)
        if not is_customer:
            audit_service.record("order.cancel", "sales_order", order.id, {"status": old_status},
                                 {"status": OrderStatus.CANCELLED, "reason": reason}, actor)
        db.session.commit()
    except Exception:
        db.session.rollback()
        raise
    return order


def _settle_payment_on_cancel(order):
    """Thanh toán online đang chờ -> thất bại; đã thu tiền -> chuyển 'đã hoàn tiền' (sandbox: hoàn thủ công qua cổng)."""
    payment = order.latest_payment
    if payment is None:
        return
    if payment.status == PaymentStatus.PENDING:
        payment.status = PaymentStatus.FAILED
    elif payment.status == PaymentStatus.PAID:
        payment.status = PaymentStatus.REFUNDED


def payment_timeout_minutes():
    return AppSetting.payment_timeout_minutes(current_app.config["DEFAULT_PAYMENT_TIMEOUT_MINUTES"])


def payment_deadline(order):
    """Thời điểm hết hạn thanh toán online = created_at + thời gian giữ hàng (suy diễn, không lưu)."""
    if order.status != OrderStatus.PENDING_PAYMENT:
        return None
    return order.created_at + timedelta(minutes=payment_timeout_minutes())


def expire_unpaid_orders(now=None):
    """FR-HT01: tự hủy đơn online chưa thanh toán quá hạn và nhả hàng. Mỗi đơn một transaction riêng.
    An toàn khi chạy lặp hoặc chạy chồng nhau (chuyển trạng thái nguyên tử). Trả về số đơn đã hủy."""
    cutoff = (now or utcnow()) - timedelta(minutes=payment_timeout_minutes())
    ids = db.session.scalars(select(SalesOrder.id).where(
        SalesOrder.status == OrderStatus.PENDING_PAYMENT, SalesOrder.created_at <= cutoff)).all()
    cancelled = 0
    for order_id in ids:
        try:
            order = db.session.get(SalesOrder, order_id)
            cancel_order(order, actor=None, reason="Quá hạn thanh toán online, hệ thống tự hủy")
            cancelled += 1
        except OrderStateError:
            db.session.rollback()          # đơn vừa được thanh toán/hủy bởi luồng khác: bỏ qua
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Không tự hủy được đơn id=%s", order_id)
    return cancelled


# ================================================================== truy vấn đơn
def list_orders(account, status=None, page=1):
    stmt = (select(SalesOrder).where(SalesOrder.account_id == account.id)
            .options(selectinload(SalesOrder.items).selectinload(SalesOrderItem.variant)
                     .selectinload(ProductVariant.product), selectinload(SalesOrder.payments))
            .order_by(SalesOrder.created_at.desc(), SalesOrder.id.desc()))
    if status in OrderStatus.ALL:
        stmt = stmt.where(SalesOrder.status == status)
    return db.paginate(stmt, page=page, per_page=current_app.config["ORDERS_PER_PAGE"], error_out=False)


def get_owned_order(account, order_code):
    """Khách hàng chỉ xem được đơn của mình; đơn người khác hoặc không tồn tại đều trả 404."""
    order = db.session.scalar(
        select(SalesOrder).where(SalesOrder.order_code == order_code, SalesOrder.account_id == account.id)
        .options(selectinload(SalesOrder.items).selectinload(SalesOrderItem.variant)
                 .selectinload(ProductVariant.product),
                 selectinload(SalesOrder.items).selectinload(SalesOrderItem.variant)
                 .selectinload(ProductVariant.size),
                 selectinload(SalesOrder.items).selectinload(SalesOrderItem.variant)
                 .selectinload(ProductVariant.color),
                 selectinload(SalesOrder.items).selectinload(SalesOrderItem.review),
                 selectinload(SalesOrder.status_history), selectinload(SalesOrder.payments),
                 selectinload(SalesOrder.shipment),
                 selectinload(SalesOrder.return_requests).selectinload(ReturnRequest.items)))
    if order is None:
        abort(404)
    return order


def can_customer_cancel(order):
    return order.status in CUSTOMER_CANCELLABLE_STATUSES


def status_counts(account):
    """Số đơn theo từng trạng thái (hiển thị trên các thẻ lọc)."""
    rows = db.session.execute(select(SalesOrder.status, func.count(SalesOrder.id))
                              .where(SalesOrder.account_id == account.id).group_by(SalesOrder.status)).all()
    return {status: n for status, n in rows}
