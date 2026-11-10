"""Sổ địa chỉ nhận hàng (FR-KH04, R03, R05).
Quy tắc: không sửa đè địa chỉ đã gắn đơn hàng; sửa = tạo địa chỉ mới, bản cũ is_active = false."""
from flask import abort, current_app
from sqlalchemy import exists, select, update
from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models import Address, Province, SalesOrder, Ward
from app.utils.validators import normalize_phone


class AddressLimitError(Exception):
    pass


def list_provinces():
    return db.session.scalars(select(Province).order_by(Province.name)).all()


def list_wards(province_id):
    return db.session.scalars(select(Ward).where(Ward.province_id == province_id).order_by(Ward.name)).all()


def list_active_addresses(account):
    """Địa chỉ đang dùng: mặc định lên đầu, sau đó mới tạo trước."""
    return db.session.scalars(
        select(Address)
        .where(Address.account_id == account.id, Address.is_active.is_(True))
        .options(joinedload(Address.ward).joinedload(Ward.province))
        .order_by(Address.is_default.desc(), Address.id.desc())
    ).all()


def get_owned_address(account, address_id):
    """Chống truy cập địa chỉ của người khác (IDOR): không thuộc tài khoản hoặc đã xóa -> 404."""
    address = db.session.scalar(
        select(Address).where(Address.id == address_id, Address.account_id == account.id,
                              Address.is_active.is_(True)))
    if address is None:
        abort(404)
    return address


def has_orders(address):
    return bool(db.session.scalar(select(exists().where(SalesOrder.address_id == address.id))))


def _set_default(account, address):
    db.session.execute(
        update(Address).where(Address.account_id == account.id, Address.is_active.is_(True))
        .values(is_default=False))
    address.is_default = True


def create_address(account, recipient_name, phone, ward_id, street_detail, make_default=False):
    active = list_active_addresses(account)
    if len(active) >= current_app.config["MAX_ADDRESSES_PER_ACCOUNT"]:
        raise AddressLimitError(
            f"Bạn chỉ có thể lưu tối đa {current_app.config['MAX_ADDRESSES_PER_ACCOUNT']} địa chỉ. "
            "Vui lòng xóa bớt địa chỉ không dùng.")
    address = Address(account_id=account.id, ward_id=ward_id, recipient_name=recipient_name.strip(),
                      phone=normalize_phone(phone), street_detail=street_detail.strip(),
                      is_default=False, is_active=True)
    db.session.add(address)
    db.session.flush()
    if make_default or not active:                 # địa chỉ đầu tiên luôn là mặc định
        _set_default(account, address)
    db.session.commit()
    return address


def update_address(account, address, recipient_name, phone, ward_id, street_detail, make_default=False):
    """Chưa gắn đơn nào: sửa trực tiếp. Đã gắn đơn: giữ nguyên bản cũ (ngừng dùng) và tạo bản mới."""
    if has_orders(address):
        was_default = address.is_default
        address.is_active = False
        address.is_default = False
        target = Address(account_id=account.id, ward_id=ward_id, recipient_name=recipient_name.strip(),
                         phone=normalize_phone(phone), street_detail=street_detail.strip(),
                         is_default=False, is_active=True)
        db.session.add(target)
        db.session.flush()
        make_default = make_default or was_default
    else:
        target = address
        target.ward_id = ward_id
        target.recipient_name = recipient_name.strip()
        target.phone = normalize_phone(phone)
        target.street_detail = street_detail.strip()
    if make_default:
        _set_default(account, target)
    db.session.commit()
    return target


def set_default(account, address):
    _set_default(account, address)
    db.session.commit()


def delete_address(account, address):
    """Xóa mềm: đơn cũ vẫn tham chiếu được địa chỉ này. Nếu xóa địa chỉ mặc định thì chuyển mặc định sang địa chỉ mới nhất còn lại."""
    was_default = address.is_default
    address.is_active = False
    address.is_default = False
    db.session.flush()
    if was_default:
        remaining = list_active_addresses(account)
        if remaining:
            _set_default(account, remaining[0])
    db.session.commit()
