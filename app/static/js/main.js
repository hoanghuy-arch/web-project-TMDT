// Gửi kèm CSRF token cho các request fetch/AJAX (Flask-WTF đọc header X-CSRFToken)
window.szFetch = function (url, options) {
  const token = document.querySelector('meta[name="csrf-token"]').content;
  options = options || {};
  options.headers = Object.assign({ "X-CSRFToken": token }, options.headers || {});
  options.credentials = "same-origin";
  return fetch(url, options);
};
