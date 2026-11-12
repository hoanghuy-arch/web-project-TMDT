"""Kiểm tra tĩnh cách dùng model: mọi `Model.thuộc_tính` và mọi tham số `Model(tham_số=...)` trong app/ và tests/
phải là cột, quan hệ, property hoặc phương thức có thật của model. Bắt lỗi gõ sai/đã đổi tên cột (ví dụ sau khi
chỉnh ERD) mà không cần chạy ứng dụng. Chạy: python scripts/check_model_usage.py"""
import ast
import glob
import os
import sys

MIXINS = {
    "TimestampMixin": {"created_at", "updated_at"},
    "UserMixin": {"is_authenticated", "is_active", "is_anonymous", "get_id"},
}
SQLA_BUILTIN = {"query", "metadata", "registry", "__table__", "__tablename__", "__mapper__", "__table_args__", "__name__",
                "__class__", "__dict__", "__init__", "__repr__", "__doc__"}

models = {}                                  # tên lớp -> tập thuộc tính hợp lệ
for path in sorted(glob.glob("app/models/*.py")):
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        bases = {getattr(b, "id", getattr(b, "attr", "")) for b in node.bases}
        if "Model" not in bases:
            continue
        attrs = set(SQLA_BUILTIN)
        for b in bases:
            attrs |= MIXINS.get(b, set())
        for st in node.body:
            if isinstance(st, ast.Assign):
                for t in st.targets:
                    if isinstance(t, ast.Name):
                        attrs.add(t.id)
            elif isinstance(st, (ast.FunctionDef, ast.AsyncFunctionDef)):
                attrs.add(st.name)
        models[node.name] = attrs

errors = []
checked = 0
for root in ("app", "tests"):
    for base, _d, files in os.walk(root):
        if "__pycache__" in base:
            continue
        for f in files:
            if not f.endswith(".py") or (root == "app" and base.startswith("app/models")):
                continue
            path = os.path.join(base, f)
            tree = ast.parse(open(path, encoding="utf-8").read(), path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in models:
                    checked += 1
                    if node.attr not in models[node.value.id]:
                        errors.append(f"{path}:{node.lineno}: {node.value.id}.{node.attr} không tồn tại trong model")
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in models:
                    for kw in node.keywords:
                        if kw.arg is None:
                            continue
                        checked += 1
                        if kw.arg not in models[node.func.id]:
                            errors.append(f"{path}:{node.lineno}: {node.func.id}({kw.arg}=...) không tồn tại trong model")

print(f"Model: {len(models)} | lượt kiểm tra: {checked}")
if errors:
    print("LỖI:")
    for e in sorted(set(errors)):
        print(" -", e)
    sys.exit(1)
print("OK: mọi thuộc tính và tham số khởi tạo model đều tồn tại.")
