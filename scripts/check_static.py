"""Kiểm tra tĩnh toàn dự án mà KHÔNG cần cài thư viện bên thứ ba. Bổ sung cho `compileall` (chỉ bắt lỗi cú pháp):
  1. Tên chưa định nghĩa (NameError khi chạy), ví dụ gõ sai __name__.
  2. `from app.x import y` / `from tests.x import y` trỏ tới thứ không tồn tại (module, hàm, lớp, biến).
  3. `import app.x` trỏ tới module không có.
Chạy: python scripts/check_static.py"""
import ast
import builtins
import os
import symtable
import sys

ROOTS = ("app", "tests", "scripts")
EXTRA_OK = {"__file__", "__name__", "__doc__", "__package__", "__spec__", "__path__", "__builtins__", "__class__"}
errors = []


def py_files():
    for root in ROOTS:
        for base, _dirs, files in os.walk(root):
            if "__pycache__" in base:
                continue
            for f in sorted(files):
                if f.endswith(".py"):
                    yield os.path.join(base, f)
    for f in ("config.py", "wsgi.py"):
        if os.path.exists(f):
            yield f


def module_path(dotted):
    """app.services.order_service -> file hoặc package tương ứng (None nếu không có)."""
    base = dotted.replace(".", os.sep)
    if os.path.isfile(base + ".py"):
        return base + ".py"
    if os.path.isfile(os.path.join(base, "__init__.py")):
        return os.path.join(base, "__init__.py")
    return None


_defined_cache = {}


def defined_names(path):
    """Tên được định nghĩa ở cấp module của file (import, def, class, gán, for, with, try...)."""
    if path in _defined_cache:
        return _defined_cache[path]
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    names = set()

    def add_target(t):
        for n in ast.walk(t):
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store):
                names.add(n.id)

    def visit(body):
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Import):
                names.update((a.asname or a.name.split(".")[0]) for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                names.update((a.asname or a.name) for a in node.names)
            elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                for t in (node.targets if isinstance(node, ast.Assign) else [node.target]):
                    add_target(t)
            elif isinstance(node, (ast.For, ast.AsyncFor)):
                add_target(node.target); visit(node.body); visit(node.orelse)
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                for item in node.items:
                    if item.optional_vars is not None:
                        add_target(item.optional_vars)
                visit(node.body)
            elif isinstance(node, ast.If):
                visit(node.body); visit(node.orelse)
            elif isinstance(node, ast.Try):
                visit(node.body); visit(node.orelse); visit(node.finalbody)
                for h in node.handlers:
                    if h.name:
                        names.add(h.name)
                    visit(h.body)
            elif isinstance(node, ast.While):
                visit(node.body); visit(node.orelse)

    visit(tree.body)
    # Python 3.12 gộp phạm vi comprehension vào phạm vi cha: biến lặp của chúng cũng là tên hợp lệ
    for n in ast.walk(tree):
        if isinstance(n, ast.comprehension):
            add_target(n.target)
    _defined_cache[path] = names
    return names


def check_undefined_names(path):
    src = open(path, encoding="utf-8").read()
    top = symtable.symtable(src, path, "exec")
    ok = defined_names(path) | set(dir(builtins)) | EXTRA_OK

    def walk(table):
        for sym in table.get_symbols():
            name = sym.get_name()
            if not sym.is_referenced() or name in ok:
                continue
            is_module = table.get_type() == "module"
            local = sym.is_local() and not is_module and (sym.is_assigned() or sym.is_parameter() or sym.is_imported() or sym.is_namespace())
            if local or sym.is_free():
                continue
            if is_module or sym.is_global():
                errors.append(f"{path}: tên chưa định nghĩa '{name}' (trong {table.get_type()} {table.get_name()})")
        for child in table.get_children():
            walk(child)

    walk(top)


def check_imports(path):
    tree = ast.parse(open(path, encoding="utf-8").read(), path)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0 and node.module.split(".")[0] in ("app", "tests", "config"):
            target = module_path(node.module)
            if target is None:
                errors.append(f"{path}:{node.lineno}: import module không tồn tại '{node.module}'")
                continue
            names = defined_names(target)
            for alias in node.names:
                if alias.name == "*" or alias.name in names:
                    continue
                if module_path(f"{node.module}.{alias.name}"):          # from app.services import order_service
                    continue
                errors.append(f"{path}:{node.lineno}: '{alias.name}' không có trong {node.module}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in ("app", "tests") and module_path(alias.name) is None:
                    errors.append(f"{path}:{node.lineno}: import module không tồn tại '{alias.name}'")


files = list(py_files())
for f in files:
    check_undefined_names(f)
    check_imports(f)

if errors:
    print("LỖI:")
    for e in sorted(set(errors)):
        print(" -", e)
    sys.exit(1)
print(f"OK: {len(files)} file, không có tên chưa định nghĩa, mọi import nội bộ đều trỏ đúng.")
