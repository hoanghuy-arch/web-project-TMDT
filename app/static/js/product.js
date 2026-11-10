// Chọn biến thể (màu + kích cỡ) ở trang chi tiết sản phẩm và hiển thị tình trạng còn hàng.
(function () {
  "use strict";

  // Đổi ảnh chính khi bấm ảnh nhỏ
  var mainImage = document.getElementById("main-image");
  document.querySelectorAll(".sz-thumb").forEach(function (btn) {
    btn.addEventListener("click", function () {
      if (mainImage) { mainImage.src = btn.dataset.full; }
    });
  });

  var dataEl = document.getElementById("variants-data");
  var root = document.getElementById("product-options");
  if (!dataEl || !root) { return; }

  var variants = JSON.parse(dataEl.textContent);
  var lowStock = parseInt(root.dataset.lowStock, 10) || 5;
  var statusEl = document.getElementById("stock-status");
  var variantInput = document.getElementById("variant_id");
  var addBtn = document.getElementById("add-to-cart-btn");
  var colorNameEl = document.getElementById("selected-color-name");
  var qtyInput = document.getElementById("quantity");
  var maxPerItem = parseInt(root.dataset.maxPerItem, 10) || 10;

  function checked(name) {
    var el = root.querySelector('input[name="' + name + '"]:checked');
    return el ? parseInt(el.value, 10) : null;
  }

  function findVariant(colorId, sizeId) {
    for (var i = 0; i < variants.length; i++) {
      if (variants[i].color_id === colorId && variants[i].size_id === sizeId) { return variants[i]; }
    }
    return null;
  }

  // Kích cỡ nào không còn hàng ở màu đang chọn thì làm mờ và không cho chọn
  function refreshSizes() {
    var colorId = checked("color");
    root.querySelectorAll('input[name="size"]').forEach(function (input) {
      var v = colorId === null ? null : findVariant(colorId, parseInt(input.value, 10));
      var unavailable = colorId !== null && (!v || v.available <= 0);
      input.disabled = unavailable;
      var label = root.querySelector('label[for="' + input.id + '"]');
      if (label) { label.classList.toggle("sz-unavailable", unavailable); }
      if (unavailable && input.checked) { input.checked = false; }
    });
  }

  function setStatus(text, cls) {
    statusEl.textContent = text;
    statusEl.className = "mb-3 small " + cls;
  }

  function refresh() {
    refreshSizes();
    var colorId = checked("color"), sizeId = checked("size");
    var colorInput = root.querySelector('input[name="color"]:checked');
    colorNameEl.textContent = colorInput ? colorInput.dataset.name : "Chọn màu";

    var v = (colorId !== null && sizeId !== null) ? findVariant(colorId, sizeId) : null;
    variantInput.value = (v && v.available > 0) ? v.id : "";
    var canBuy = !!(v && v.available > 0);
    if (addBtn) { addBtn.disabled = !canBuy; }
    if (qtyInput) {                                  // số lượng tối đa = min(tồn khả dụng, giới hạn mỗi sản phẩm)
      qtyInput.disabled = !canBuy;
      qtyInput.max = canBuy ? Math.min(v.available, maxPerItem) : 1;
      if (!canBuy || parseInt(qtyInput.value, 10) > parseInt(qtyInput.max, 10)) { qtyInput.value = 1; }
    }

    if (colorId === null || sizeId === null) {
      setStatus("Vui lòng chọn màu và kích cỡ.", "text-muted");
    } else if (!v || v.available <= 0) {
      setStatus("Phiên bản này đã hết hàng.", "text-danger");
    } else if (v.available <= lowStock) {
      setStatus("Sắp hết hàng: chỉ còn " + v.available + " sản phẩm.", "text-warning fw-semibold");
    } else {
      setStatus("Còn hàng.", "text-success fw-semibold");
    }
  }

  root.addEventListener("change", refresh);

  // Chỉ có một lựa chọn thì chọn sẵn cho khách
  ["color", "size"].forEach(function (name) {
    var inputs = root.querySelectorAll('input[name="' + name + '"]:not(:disabled)');
    if (inputs.length === 1) { inputs[0].checked = true; }
  });
  refresh();
})();
