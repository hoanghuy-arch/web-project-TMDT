"""Kiểm thử models: ràng buộc DB, khóa tài khoản, bản ghi chỉ-thêm, máy trạng thái."""
from datetime import timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.constants import (OrderStatus, PaymentMethod, PaymentStatus, ROLE_ADMIN, ROLE_CUSTOMER,
                           ROLE_STAFF, Perm, StockTxType, can_transition,
                           CUSTOMER_CANCELLABLE_STATUSES, STAFF_CANCELLABLE_STATUSES)
from app.extensions import db
from app.models import (Account, Address, AuditLog, Category, Color, Permission, Product,
                        ProductVariant, Promotion, Province, Role, SalesOrder, SalesOrderItem,
                        SalesOrderStatusHistory, Size, StockTransaction, Ward, ImmutableRecordError)
from app.models.base import utcnow


# ---------- dữ liệu mẫu dùng chung ----------
@pytest.fixture()
def base_data(app):
    roles = {c: Role(name=c) for c in (ROLE_CUSTOMER, ROLE_STAFF, ROLE_ADMIN)}
    db.session.add_all(roles.values())
    prov = Province(name="TP. Hồ Chí Minh")
    ward = Ward(province=prov, name="Phường Tân Hưng")
    cat = Category(name="Áo", slug="ao")
    size, color = Size(name="M"), Color(name="Đen")
    db.session.add_all([prov, ward, cat, size, color])
    db.session.flush()

    def make_account(email, role_code):
        a = Account(email=email, full_name="Test", phone="0900000000", role=roles[role_code])
        a.set_password("MatKhau@123")
        db.session.add(a)
        return a

    a1, a2 = make_account("a1@test.com", ROLE_CUSTOMER), make_account("a2@test.com", ROLE_CUSTOMER)
    prod = Product(category=cat, name="Áo chạy bộ", slug="ao-chay-bo", price=250_000)
    db.session.add(prod)
    db.session.flush()
    var = ProductVariant(product=prod, size=size, color=color, sku="AO-M-DEN", stock_quantity=10)
    addr1 = Address(account=a1, ward=ward, recipient_name="A1", phone="0900000001", street_detail="1 Lê Lợi")
    db.session.add_all([var, addr1])
    db.session.commit()
    return dict(roles=roles, a1=a1, a2=a2, var=var, addr1=addr1, ward=ward, prod=prod)


def _order(account, address, code="SZ-0001"):
    return SalesOrder(order_code=code, account_id=account.id, address_id=address.id,
                      status=OrderStatus.PENDING_CONFIRM)


# ---------- tài khoản ----------
def test_password_is_hashed(app, base_data):
    a = base_data["a1"]
    assert a.password_hash != "MatKhau@123"
    assert a.check_password("MatKhau@123") and not a.check_password("sai")


def test_lock_after_5_failed_logins(app, base_data):
    a = base_data["a1"]
    for _ in range(5):
        a.register_failed_login(max_attempts=5, lock_minutes=15)
    assert a.is_locked
    a.locked_until = utcnow() - timedelta(minutes=1)      # hết hạn khóa
    assert not a.is_locked
    a.register_successful_login()
    assert a.failed_login_count == 0 and a.locked_until is None


def test_admin_has_all_permissions_staff_only_granted(app, base_data):
    perm = Permission(code=Perm.STOCK_RECEIPT, description="Lập phiếu nhập")
    staff_role = base_data["roles"][ROLE_STAFF]
    staff_role.permissions.append(perm)
    staff = Account(email="nv@test.com", full_name="NV", phone="0911111111", role=staff_role)
    staff.set_password("x")
    admin = Account(email="ad@test.com", full_name="AD", phone="0922222222", role=base_data["roles"][ROLE_ADMIN])
    admin.set_password("x")
    db.session.add_all([staff, admin])
    db.session.commit()
    assert staff.has_permission(Perm.STOCK_RECEIPT) and not staff.has_permission(Perm.USER_MANAGE)
    assert admin.has_permission(Perm.USER_MANAGE)


def test_duplicate_email_rejected(app, base_data):
    dup = Account(email="a1@test.com", full_name="Dup", phone="0933333333",
                  role=base_data["roles"][ROLE_CUSTOMER], password_hash="x")
    db.session.add(dup)
    with pytest.raises(IntegrityError):
        db.session.commit()


# ---------- tồn kho ----------
def test_available_quantity(app, base_data):
    v = base_data["var"]
    v.reserved_quantity = 3
    db.session.commit()
    assert v.available_quantity == 7


@pytest.mark.parametrize("stock,reserved", [(-1, 0), (5, -1), (5, 6)])
def test_variant_stock_constraints(app, base_data, stock, reserved):
    v = base_data["var"]
    v.stock_quantity, v.reserved_quantity = stock, reserved
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_variant_unique_product_size_color(app, base_data):
    v = base_data["var"]
    db.session.add(ProductVariant(product_id=v.product_id, size_id=v.size_id, color_id=v.color_id,
                                  sku="KHAC", stock_quantity=1))
    with pytest.raises(IntegrityError):
        db.session.commit()


# ---------- đơn hàng ----------
def test_order_totals_are_derived(app, base_data):
    o = _order(base_data["a1"], base_data["addr1"])
    o.discount_amount, o.shipping_fee = 20_000, 30_000
    o.items.append(SalesOrderItem(product_variant_id=base_data["var"].id, quantity=2, unit_price=250_000))
    db.session.add(o)
    db.session.commit()
    assert o.subtotal == 500_000
    assert o.total_amount == 510_000         # 500.000 - 20.000 + 30.000


def test_order_address_must_belong_to_account(app, base_data):
    """Khóa ngoại kép (address_id, account_id): a2 không được dùng địa chỉ của a1."""
    db.session.add(_order(base_data["a2"], base_data["addr1"]))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_order_item_unique_variant_per_order(app, base_data):
    o = _order(base_data["a1"], base_data["addr1"])
    o.items.append(SalesOrderItem(product_variant_id=base_data["var"].id, quantity=1, unit_price=1))
    o.items.append(SalesOrderItem(product_variant_id=base_data["var"].id, quantity=1, unit_price=1))
    db.session.add(o)
    with pytest.raises(IntegrityError):
        db.session.commit()


# ---------- bản ghi chỉ thêm ----------
def test_status_history_is_append_only(app, base_data):
    o = _order(base_data["a1"], base_data["addr1"])
    db.session.add(o)
    db.session.flush()
    h = SalesOrderStatusHistory(sales_order_id=o.id, to_status=OrderStatus.PENDING_CONFIRM)
    db.session.add(h)
    db.session.commit()
    h.reason = "sửa lén"
    with pytest.raises(ImmutableRecordError):
        db.session.commit()
    db.session.rollback()
    db.session.delete(h)
    with pytest.raises(ImmutableRecordError):
        db.session.commit()


def test_audit_log_is_append_only(app, base_data):
    log = AuditLog(action="order.cancel", entity_name="sales_order", entity_id=1,
                   old_value={"status": "CONFIRMED"}, new_value={"status": "CANCELLED"}, ip_address="127.0.0.1")
    db.session.add(log)
    db.session.commit()
    log.action = "khac"
    with pytest.raises(ImmutableRecordError):
        db.session.commit()


def test_stock_transaction_single_source(app, base_data):
    o = _order(base_data["a1"], base_data["addr1"])
    db.session.add(o)
    db.session.flush()
    ok = StockTransaction(product_variant_id=base_data["var"].id, transaction_type=StockTxType.RESERVE,
                          reserved_delta=1, sales_order_id=o.id)
    db.session.add(ok)
    db.session.commit()
    # Không có nguồn nào cũng hợp lệ (điều chỉnh thủ công)
    db.session.add(StockTransaction(product_variant_id=base_data["var"].id, transaction_type=StockTxType.ADJUST,
                                    stock_delta=-1, note="kiểm kê"))
    db.session.commit()


# ---------- thanh toán / khuyến mãi ----------
def test_payment_status_check(app, base_data):
    from app.models import Payment
    o = _order(base_data["a1"], base_data["addr1"])
    db.session.add(o)
    db.session.flush()
    db.session.add(Payment(sales_order_id=o.id, method=PaymentMethod.COD, status="BAD", amount=1))
    with pytest.raises(IntegrityError):
        db.session.commit()


def test_promotion_period_check(app):
    now = utcnow()
    db.session.add(Promotion(code="X", name="X", discount_type="PERCENT", discount_value=10,
                             start_at=now, end_at=now - timedelta(days=1)))
    with pytest.raises(IntegrityError):
        db.session.commit()


# ---------- máy trạng thái đơn hàng (thuần Python), đúng Hình 2.6 ----------
@pytest.mark.parametrize("src,dst,ok", [
    (OrderStatus.PENDING_PAYMENT, OrderStatus.PENDING_CONFIRM, True),
    (OrderStatus.PENDING_PAYMENT, OrderStatus.CANCELLED, True),
    (OrderStatus.PENDING_CONFIRM, OrderStatus.CONFIRMED, True),
    (OrderStatus.PENDING_CONFIRM, OrderStatus.CANCELLED, True),
    (OrderStatus.CONFIRMED, OrderStatus.PACKING, True),
    (OrderStatus.CONFIRMED, OrderStatus.CANCELLED, True),
    (OrderStatus.PACKING, OrderStatus.SHIPPING, True),
    (OrderStatus.PACKING, OrderStatus.CANCELLED, True),
    (OrderStatus.SHIPPING, OrderStatus.COMPLETED, True),
    (OrderStatus.COMPLETED, OrderStatus.RETURNING, True),
    (OrderStatus.RETURNING, OrderStatus.RETURNED, True),
    (OrderStatus.SHIPPING, OrderStatus.CANCELLED, False),        # đang giao không được hủy trực tiếp
    (OrderStatus.CANCELLED, OrderStatus.CONFIRMED, False),       # trạng thái kết thúc
    (OrderStatus.PENDING_CONFIRM, OrderStatus.SHIPPING, False),  # nhảy cóc
    (OrderStatus.PENDING_PAYMENT, OrderStatus.CONFIRMED, False), # phải qua Chờ xác nhận
    (OrderStatus.COMPLETED, OrderStatus.CANCELLED, False),
    (OrderStatus.RETURNING, OrderStatus.COMPLETED, False),       # sơ đồ không có đường quay lại
    (OrderStatus.RETURNED, OrderStatus.COMPLETED, False),
])
def test_order_transitions(src, dst, ok):
    assert can_transition(src, dst) is ok


def test_cancel_rules_by_actor():
    # Khách: Chờ xác nhận, Đã xác nhận. Đang đóng gói chỉ nhân viên/quản trị viên (kèm lý do)
    assert OrderStatus.PENDING_CONFIRM in CUSTOMER_CANCELLABLE_STATUSES
    assert OrderStatus.CONFIRMED in CUSTOMER_CANCELLABLE_STATUSES
    assert OrderStatus.PACKING not in CUSTOMER_CANCELLABLE_STATUSES
    assert OrderStatus.PACKING in STAFF_CANCELLABLE_STATUSES
    assert OrderStatus.SHIPPING not in STAFF_CANCELLABLE_STATUSES
