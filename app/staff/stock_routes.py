"""Tồn kho, phiếu nhập kho, điều chỉnh tồn kho (FR-NV06, FR-NV07, FR-QT05)."""
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user

from app.constants import Perm, ReceiptStatus, StockTxType
from app.services import catalog_service, stock_service
from app.services.errors import ConcurrentUpdateError, StockError
from app.staff import bp
from app.utils.decorators import permission_required


# ------------------------------------------------------------------ tồn kho
@bp.route("/stock")
@permission_required(Perm.STOCK_VIEW)
def stock():
    q = " ".join(request.args.get("q", "").split())[:100]
    low = request.args.get("low") == "1"
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = stock_service.search_variants(q, low, page)
    if pagination.total and not pagination.items:
        return redirect(url_for("staff.stock", q=q or None, low=1 if low else None,
                                page=pagination.pages if pagination.pages > 1 else None))
    return render_template("staff/stock.html", pagination=pagination, variants=pagination.items, q=q, low=low,
                           threshold=catalog_service.low_stock_threshold(),
                           list_url=lambda p: url_for("staff.stock", q=q or None, low=1 if low else None, page=p if p > 1 else None))


@bp.route("/stock/<int:variant_id>")
@permission_required(Perm.STOCK_VIEW)
def stock_detail(variant_id):
    variant = stock_service.get_variant(variant_id)
    return render_template("staff/stock_detail.html", variant=variant, transactions=stock_service.recent_transactions(variant),
                           threshold=catalog_service.low_stock_threshold(), tx_labels=StockTxType.LABELS)


@bp.route("/stock/<int:variant_id>/adjust", methods=["POST"])
@permission_required(Perm.STOCK_ADJUST)
def stock_adjust(variant_id):
    variant = stock_service.get_variant(variant_id)
    raw = request.form.get("delta", "").strip()
    delta = int(raw) if raw.lstrip("+-").isdigit() and raw.lstrip("+-") else None
    try:
        stock_service.adjust(variant, current_user, delta, request.form.get("reason", ""))
    except StockError as e:
        flash(str(e), "danger")
    else:
        flash("Đã điều chỉnh tồn kho và ghi nhật ký.", "success")
    return redirect(url_for("staff.stock_detail", variant_id=variant_id))


# ------------------------------------------------------------------ phiếu nhập
@bp.route("/receipts")
@permission_required(Perm.STOCK_VIEW)
def receipts():
    status = request.args.get("status", "")
    status = status if status in ReceiptStatus.ALL else None
    page = max(request.args.get("page", 1, type=int), 1)
    pagination = stock_service.list_receipts(status, page)
    if pagination.total and not pagination.items:
        return redirect(url_for("staff.receipts", status=status, page=pagination.pages if pagination.pages > 1 else None))
    return render_template("staff/receipts.html", pagination=pagination, receipts=pagination.items, status=status,
                           labels=ReceiptStatus.LABELS,
                           list_url=lambda p: url_for("staff.receipts", status=status, page=p if p > 1 else None))


def _to_int(raw):
    raw = (raw or "").strip()
    return int(raw) if raw.isdigit() else None


@bp.route("/receipts/new", methods=["GET", "POST"])
@permission_required(Perm.STOCK_RECEIPT)
def receipt_new():
    rows, supplier_id, note = [{"sku": "", "qty": "", "cost": ""}] * 3, request.form.get("supplier_id", type=int), ""
    if request.method == "POST":
        note = request.form.get("note", "")
        indexes = sorted({k.split("_", 1)[1] for k in request.form if k.startswith("sku_")}, key=lambda x: int(x) if x.isdigit() else 0)
        rows = [{"sku": request.form.get(f"sku_{i}", ""), "qty": request.form.get(f"qty_{i}", ""),
                 "cost": request.form.get(f"cost_{i}", "")} for i in indexes] or rows
        lines = [(r["sku"], _to_int(r["qty"]), _to_int(r["cost"].replace(".", "").replace(",", ""))) for r in rows]
        try:
            receipt = stock_service.create_receipt(current_user, supplier_id, note, lines)
        except StockError as e:
            flash(str(e), "danger")
        else:
            flash(f"Đã lập phiếu nhập {receipt.receipt_code}. Nhập số lượng thực nhận khi hàng về để xác nhận nhập kho.", "success")
            return redirect(url_for("staff.receipt_detail", receipt_id=receipt.id))
    return render_template("staff/receipt_form.html", suppliers=stock_service.active_suppliers(), rows=rows,
                           supplier_id=supplier_id, note=note)


@bp.route("/receipts/<int:receipt_id>")
@permission_required(Perm.STOCK_VIEW)
def receipt_detail(receipt_id):
    return render_template("staff/receipt_detail.html", receipt=stock_service.get_receipt(receipt_id))


@bp.route("/receipts/<int:receipt_id>/confirm", methods=["POST"])
@permission_required(Perm.STOCK_RECEIPT)
def receipt_confirm(receipt_id):
    receipt = stock_service.get_receipt(receipt_id)
    received = {item.id: _to_int(request.form.get(f"received_{item.id}")) for item in receipt.items}
    try:
        stock_service.confirm_receipt(receipt, current_user, received)
    except (StockError, ConcurrentUpdateError) as e:
        flash(str(e), "danger")
    else:
        flash("Đã xác nhận nhập kho: số lượng thực nhận đã được cộng vào tồn kho.", "success")
    return redirect(url_for("staff.receipt_detail", receipt_id=receipt_id))


@bp.route("/receipts/<int:receipt_id>/cancel", methods=["POST"])
@permission_required(Perm.STOCK_RECEIPT)
def receipt_cancel(receipt_id):
    receipt = stock_service.get_receipt(receipt_id)
    try:
        stock_service.cancel_receipt(receipt, current_user)
    except (StockError, ConcurrentUpdateError) as e:
        flash(str(e), "danger")
    else:
        flash("Đã hủy phiếu nhập.", "info")
    return redirect(url_for("staff.receipt_detail", receipt_id=receipt_id))
