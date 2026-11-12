// Phiếu nhập: thêm dòng hàng mới (tối đa theo data-max-lines).
(function () {
  "use strict";
  var table = document.getElementById("receipt-lines");
  var button = document.getElementById("add-line");
  if (!table || !button) { return; }
  var body = table.tBodies[0];
  var max = parseInt(table.dataset.maxLines, 10) || 50;

  button.addEventListener("click", function () {
    var count = body.rows.length;
    if (count >= max) { return; }
    var n = count + 1;
    var row = body.rows[0].cloneNode(true);
    row.querySelectorAll("input").forEach(function (input) {
      input.name = input.name.replace(/_\d+$/, "_" + n);   // sku_N, qty_N, cost_N
      input.value = "";
    });
    body.appendChild(row);
    if (body.rows.length >= max) { button.disabled = true; }
  });
})();
