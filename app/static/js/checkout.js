// Đổi địa chỉ nhận hàng thì tính lại phí vận chuyển (gửi form ở chế độ xem trước, chưa đặt hàng).
(function () {
  "use strict";
  var form = document.getElementById("checkout-form");
  if (!form) { return; }
  form.addEventListener("change", function (e) {
    if (e.target && e.target.name === "address_id") {
      var hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "action";
      hidden.value = "apply";
      form.appendChild(hidden);
      form.submit();
    }
  });
})();
