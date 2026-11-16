"""Kiểm thử tích hợp Giao Hàng Nhanh (GHN Open API & Tracking)."""
from datetime import datetime
from decimal import Decimal
import pytest

from app.constants import OrderStatus, PaymentMethod, PaymentStatus
from app.extensions import db
from app.models import Carrier, SalesOrder, Shipment
from app.services import ghn_service, order_service, fulfillment_service
from tests.helpers import COD, make_variant, put_in_cart, place


def test_calculate_shipping_options(app, shop, buyer):
    acc, addr = buyer
    options = ghn_service.calculate_shipping_options(addr, Decimal(250000))
    assert len(options) == 2
    codes = [opt.code for opt in options]
    assert "GHN_STANDARD" in codes and "GHN_EXPRESS" in codes

    std = next(opt for opt in options if opt.code == "GHN_STANDARD")
    exp = next(opt for opt in options if opt.code == "GHN_EXPRESS")

    assert std.name == "Giao Tiêu Chuẩn (GHN)"
    assert exp.name == "Giao Nhanh (GHN Express)"
    assert "Dự kiến" in std.leadtime_text
    assert "Dự kiến" in exp.leadtime_text
    assert std.leadtime_date > datetime(2020, 1, 1)


def test_create_shipping_order_and_tracking(app, shop, buyer):
    acc, addr = buyer
    v = make_variant(shop, price=300000, stock=20)
    put_in_cart(acc, [(v, 1)])
    order = place(acc, addr)

    # Đơn mới đặt
    timeline = ghn_service.get_tracking_timeline(order)
    assert len(timeline["steps"]) == 5
    assert timeline["steps"][0]["label"] == "Đặt hàng thành công"
    assert timeline["steps"][0]["is_current"] is True
    assert timeline["tracking_code"] is None
    assert len(timeline["logs"]) >= 1

    # Tạo đơn vận chuyển sang GHN
    shipment = ghn_service.create_shipping_order(order, service_code="GHN_STANDARD")
    assert shipment.tracking_code.startswith("GHN")
    assert shipment.tracking_code.endswith("VN")
    assert shipment.service_name == "Giao Tiêu Chuẩn (GHN)"
    assert shipment.expected_delivery_at is not None
    assert f"/orders/{order.order_code}/shipping-label" in shipment.label_url

    # Kiểm tra lại timeline khi đã có shipment
    timeline_after = ghn_service.get_tracking_timeline(order)
    assert timeline_after["tracking_code"] == shipment.tracking_code
    assert timeline_after["carrier_name"] == "Giao Hàng Nhanh (GHN)"


def test_staff_order_ship_ghn(app, shop, buyer, staff, client):
    acc, addr = buyer
    v = make_variant(shop, price=200000, stock=10)
    put_in_cart(acc, [(v, 2)])
    order = place(acc, addr)

    # Chuyển CONFIRMED -> PACKING
    fulfillment_service.confirm_order(order, staff)
    fulfillment_service.start_packing(order, staff)
    assert order.status == OrderStatus.PACKING

    res = client.post(f"/staff/orders/{order.order_code}/ship-ghn", data={
        "service_code": "GHN_STANDARD",
        "required_note": "CHOXEMHANGKHONGTHU"
    }, follow_redirects=True)

    assert res.status_code == 200
    db.session.refresh(order)
    assert order.status == OrderStatus.SHIPPING
    assert order.shipment is not None
    assert order.shipment.tracking_code.startswith("GHN")


def test_shipping_label_page_renders_correctly(app, shop, buyer, client):
    acc, addr = buyer
    v = make_variant(shop, price=150000, stock=5)
    put_in_cart(acc, [(v, 1)])
    order = place(acc, addr)
    ghn_service.create_shipping_order(order)

    # Khách hoặc nhân viên mở trang in phiếu giao hàng
    res = client.get(f"/account/orders/{order.order_code}/shipping-label")
    assert res.status_code == 200
    body = res.get_data(as_text=True)
    assert "SPORTZONE" in body
    assert "GIAO HÀNG NHANH" in body
    assert order.order_code in body
    assert order.shipment.tracking_code in body
    assert "CHO XEM HÀNG, KHÔNG CHO THỬ" in body
    assert "TIỀN THU NGƯỜI NHẬN (COD)" in body
