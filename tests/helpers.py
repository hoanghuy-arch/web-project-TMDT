"""Hàm hỗ trợ dùng chung cho các bộ test đặt hàng và thanh toán."""
from datetime import timedelta

from app.constants import DiscountType, EntityStatus, PaymentMethod
from app.extensions import db
from app.models import Address, CartItem, Promotion
from app.models.base import utcnow
from app.services import order_service

COD, VNPAY = PaymentMethod.COD, PaymentMethod.VNPAY


def new_buyer(make_account, ward, email):
    acc = make_account(email=email)
    addr = Address(account=acc, ward=ward, recipient_name="Người Nhận", phone="0912345678",
                   street_detail="1 Lê Lợi", is_default=True)
    db.session.add(addr)
    db.session.commit()
    return acc, addr


def put_in_cart(account, items):
    for variant, qty in items:
        db.session.add(CartItem(account_id=account.id, product_variant_id=variant.id, quantity=qty))
    db.session.commit()


def make_variant(shop, name="Áo A", price=250000, stock=10, reserved=0):
    return shop["make"](name, price, shop["ao"], [(shop["m"], shop["den"], stock, reserved)]).variants[0]


def make_promo(code="SAVE10", type_=DiscountType.PERCENT, value=10, min_order=0, max_discount=None,
               limit=None, start=-1, end=30, status=EntityStatus.ACTIVE):
    p = Promotion(code=code, discount_type=type_, discount_value=value, min_order_value=min_order,
                  max_discount=max_discount, start_at=utcnow() + timedelta(days=start),
                  end_at=utcnow() + timedelta(days=end), usage_limit=limit, status=status)
    db.session.add(p)
    db.session.commit()
    return p


def place(acc, addr, method=COD, promo="", note=None):
    return order_service.place_order(acc, addr.id, promo, method, note)


def refresh(*objs):
    for o in objs:
        db.session.refresh(o)
