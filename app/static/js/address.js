// Form địa chỉ: chọn tỉnh/thành xong thì nạp danh sách phường/xã tương ứng.
(function () {
  "use strict";
  var form = document.getElementById("address-form");
  if (!form) { return; }
  var province = document.getElementById("province_id");
  var ward = document.getElementById("ward_id");
  var url = form.dataset.wardsUrl;

  function fillWards(items) {
    ward.innerHTML = "";
    var first = document.createElement("option");
    first.value = "0";
    first.textContent = "-- Chọn phường/xã --";
    ward.appendChild(first);
    items.forEach(function (w) {
      var opt = document.createElement("option");
      opt.value = String(w.id);
      opt.textContent = w.name;          // textContent: không chèn HTML từ dữ liệu
      ward.appendChild(opt);
    });
  }

  province.addEventListener("change", function () {
    var id = parseInt(province.value, 10);
    if (!id) { fillWards([]); return; }
    ward.disabled = true;
    window.szFetch(url + "?province_id=" + id, { headers: { "Accept": "application/json" } })
      .then(function (r) { if (!r.ok) { throw new Error("HTTP " + r.status); } return r.json(); })
      .then(fillWards)
      .catch(function () { fillWards([]); alert("Không tải được danh sách phường/xã. Vui lòng thử lại."); })
      .then(function () { ward.disabled = false; });
  });
})();
