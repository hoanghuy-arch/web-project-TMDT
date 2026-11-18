"""Script thêm nhanh hàng loạt sản phẩm thể thao vào hệ thống SportZone.


Cách chạy:
- Trên máy local:
    python scripts/import_products.py
- Trên máy chủ VPS (Docker):
    docker compose -f docker-compose.prod.yml exec app python scripts/import_products.py
"""
import logging
import os
import sys

# Đảm bảo đường dẫn import thư mục gốc
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.getLogger("apscheduler").setLevel(logging.CRITICAL)
logging.getLogger("werkzeug").setLevel(logging.CRITICAL)

from app import create_app
from app.constants import EntityStatus
from app.extensions import db
from app.models import Category, Color, Product, ProductImage, ProductVariant, Size


# ==============================================================================
# DANH MỤC, KÍCH CỠ, MÀU SẮC MẪU
# ==============================================================================
CATEGORIES_DATA = [
    ("Áo thể thao", "ao-the-thao", None),
    ("Quần thể thao", "quan-the-thao", None),
    ("Áo chạy bộ", "ao-chay-bo", "ao-the-thao"),
    ("Áo tập gym", "ao-tap-gym", "ao-the-thao"),
    ("Quần jogger", "quan-jogger", "quan-the-thao"),
    ("Quần đùi chạy bộ", "quan-dui-chay-bo", "quan-the-thao"),
    ("Giày thể thao", "giay-the-thao", None),
    ("Phụ kiện thể thao", "phu-kien-the-thao", None),
]

SIZES_DATA = [
    ("S", 1), ("M", 2), ("L", 3), ("XL", 4), ("XXL", 5),
    ("39", 10), ("40", 11), ("41", 12), ("42", 13), ("43", 14),
    ("FreeSize", 20)
]

COLORS_DATA = [
    ("Đen", "#000000"),
    ("Trắng", "#FFFFFF"),
    ("Xanh Navy", "#001F5B"),
    ("Đỏ", "#CC0000"),
    ("Xám", "#808080"),
    ("Xanh Rêu", "#4B5320"),
    ("Cam", "#FF6600"),
]

# ==============================================================================
# DANH SÁCH SẢN PHẨM MẪU (TẤT CẢ DÙNG ẢNH TRONG THƯ MỤC static/img/)
# Sau này bạn chỉ cần chép file ảnh vào thư mục app/static/img/ rồi đổi tên file ở đây
# ==============================================================================
SAMPLE_PRODUCTS = [
    {
        "name": "Áo Chạy Bộ Nam Pro Dri-FIT Swift",
        "slug": "ao-chay-bo-nam-pro-dri-fit-swift",
        "category_slug": "ao-chay-bo",
        "price": 320000,
        "description": "Áo chạy bộ cộc tay với công nghệ dệt sợi Dri-FIT siêu nhẹ, thoát ẩm cực nhanh. Thiết kế đường may phẳng chống cọ xát da khi vận động đường dài.",
        "images": [
            {"url": "img/ao-chay-bo-swift-den.webp", "is_primary": True},
            {"url": "img/ao-chay-bo-swift.png", "is_primary": False},
        ],
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["Đen", "Trắng", "Xanh Navy"],
        "stock_per_variant": 40
    },
    {
        "name": "Áo Tập Gym Nam Tanktop BodyFit",
        "slug": "ao-tap-gym-nam-tanktop-bodyfit",
        "category_slug": "ao-tap-gym",
        "price": 260000,
        "description": "Áo ba lỗ gym nam form tôn dáng, khoét sâu nách tạo sự thoải mái tối đa cho các bài tập tạ ngực và lưng xô. Chất thun co giãn 4 chiều mềm mịn.",
        "images": [
            {"url": "img/ao-tap-gym-tanktop.webp", "is_primary": True},
        ],
        "sizes": ["M", "L", "XL"],
        "colors": ["Đen", "Xám", "Đỏ"],
        "stock_per_variant": 35
    },
    {
        "name": "Quần Jogger Thể Thao Cao Cấp FlexPro",
        "slug": "quan-jogger-the-thao-cao-cap-flexpro",
        "category_slug": "quan-jogger",
        "price": 390000,
        "description": "Quần jogger dáng suông bo gấu trẻ trung, chất nỉ da cá dày dặn co giãn thoải mái. Túi kéo khóa zip 2 bên an toàn để điện thoại khi chạy nhảy.",
        "images": [
            {"url": "img/quan-jogger-flexpro.avif", "is_primary": True},
        ],
        "sizes": ["S", "M", "L", "XL", "XXL"],
        "colors": ["Đen", "Xám", "Xanh Navy"],
        "stock_per_variant": 50
    },
    {
        "name": "Quần Đùi 2 Lớp Chạy Bộ Marathon",
        "slug": "quan-dui-2-lop-chay-bo-marathon",
        "category_slug": "quan-dui-chay-bo",
        "price": 290000,
        "description": "Thiết kế quần 2 lớp thông minh: lớp lót ôm cơ đùi chống ma sát, lớp ngoài dù siêu nhẹ kháng nước và thông khí. Có túi sau lưng đựng chìa khóa, gel năng lượng.",
        "images": [
            {"url": "img/quan-dui-marathon.jpg", "is_primary": True},
        ],
        "sizes": ["S", "M", "L", "XL"],
        "colors": ["Đen", "Xanh Rêu"],
        "stock_per_variant": 30
    },
    {
        "name": "Giày Chạy Bộ Nam Nữ SportZone UltraBoost",
        "slug": "giay-chay-bo-nam-nu-sportzone-ultraboost",
        "category_slug": "giay-the-thao",
        "price": 890000,
        "description": "Đế đệm bọt khí đàn hồi cao trợ lực từng bước chạy. Thân giày dệt Primeknit thoáng khí, ôm khít bàn chân và giảm chấn thương gót chân hiệu quả.",
        "images": [
            {"url": "img/giay-chay-bo.webp", "is_primary": True},
        ],
        "sizes": ["39", "40", "41", "42", "43"],
        "colors": ["Đen", "Trắng", "Đỏ"],
        "stock_per_variant": 25
    },
    {
        "name": "Balo Thể Thao Đa Năng Chống Nước SportZone 25L",
        "slug": "balo-the-thao-da-nang-chong-nuoc-25l",
        "category_slug": "phu-kien-the-thao",
        "price": 450000,
        "description": "Balo thể thao chất liệu vải Oxford chống thấm nước 100%. Tích hợp ngăn riêng để giày thể thao tách biệt quần áo sạch, ngăn laptop 15.6 inch tiện lợi.",
        "images": [
            {"url": "img/balo-25l.png", "is_primary": True},
        ],
        "sizes": ["FreeSize"],
        "colors": ["Đen", "Xám"],
        "stock_per_variant": 60
    },
    {
        "name": "Bình Nước Giữ Nhiệt Thể Thao Inox 1000ml",
        "slug": "binh-nuoc-giu-nhiet-the-thao-inox-1000ml",
        "category_slug": "phu-kien-the-thao",
        "price": 195000,
        "description": "Bình giữ nhiệt Inox 304 tiêu chuẩn an toàn sức khỏe. Giữ lạnh đến 24 giờ và giữ ấm 12 giờ. Nắp bật có vòi hút tiện dụng khi đang chạy hoặc đạp xe.",
        "images": [
            {"url": "img/binh-nuoc-giu-nhiet.webp", "is_primary": True},
        ],
        "sizes": ["FreeSize"],
        "colors": ["Đen", "Trắng", "Cam"],
        "stock_per_variant": 100
    },
    {
        "name": "Găng Tay Tập Gym Nam Nữ Có Quấn Cổ Tay",
        "slug": "gang-tay-tap-gym-nam-nu-co-quan-co-tay",
        "category_slug": "phu-kien-the-thao",
        "price": 150000,
        "description": "Đệm lòng bàn tay dày chống chai sần và chống trượt tạ. Dây quấn cổ tay dài 45cm cố định khớp cổ tay an toàn trong các bài đẩy tạ nặng.",
        "images": [
            {"url": "img/gang-tay-gym.jpg", "is_primary": True},
        ],
        "sizes": ["M", "L", "XL"],
        "colors": ["Đen", "Đỏ"],
        "stock_per_variant": 40
    }
]


def run_import():
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("KHỞI CHẠY TIẾN TRÌNH IMPORT / CẬP NHẬT ẢNH SẢN PHẨM SPORTZONE")
        print("=" * 60)

        # 1. Khởi tạo Kích cỡ
        sizes = {}
        for name, order in SIZES_DATA:
            s = db.session.scalar(db.select(Size).filter_by(name=name))
            if not s:
                s = Size(name=name, sort_order=order)
                db.session.add(s)
                print(f"[+] Tạo kích cỡ: {name}")
            sizes[name] = s
        db.session.flush()

        # 2. Khởi tạo Màu sắc
        colors = {}
        for name, hex_code in COLORS_DATA:
            c = db.session.scalar(db.select(Color).filter_by(name=name))
            if not c:
                c = Color(name=name, hex_code=hex_code)
                db.session.add(c)
                print(f"[+] Tạo màu sắc: {name} ({hex_code})")
            colors[name] = c
        db.session.flush()

        # 3. Khởi tạo Danh mục
        cats = {}
        for name, slug, parent_slug in CATEGORIES_DATA:
            cat = db.session.scalar(db.select(Category).filter_by(slug=slug))
            if not cat:
                parent_id = cats[parent_slug].id if parent_slug and parent_slug in cats else None
                cat = Category(name=name, slug=slug, parent_category_id=parent_id, is_active=True)
                db.session.add(cat)
                print(f"[+] Tạo danh mục: {name}")
            cats[slug] = cat
        db.session.flush()

        # 4. Tạo hoặc Cập nhật Sản phẩm, Ảnh và Biến thể
        created_count = 0
        updated_img_count = 0
        total_variants = 0

        for pdata in SAMPLE_PRODUCTS:
            existing = db.session.scalar(db.select(Product).filter_by(slug=pdata["slug"]))
            if existing:
                # Cập nhật lại ảnh cho sản phẩm đã có
                if pdata.get("images"):
                    db.session.execute(db.delete(ProductImage).filter_by(product_id=existing.id))
                    for idx, img in enumerate(pdata["images"]):
                        p_img = ProductImage(
                            product_id=existing.id,
                            url=img["url"],
                            is_primary=img.get("is_primary", idx == 0),
                            sort_order=idx
                        )
                        db.session.add(p_img)
                    updated_img_count += 1
                    print(f"[~] ĐÃ CẬP NHẬT ẢNH CHO: {existing.name} -> {pdata['images'][0]['url']}")
                continue

            category = cats.get(pdata["category_slug"])
            if not category:
                category = list(cats.values())[0]

            product = Product(
                name=pdata["name"],
                slug=pdata["slug"],
                category_id=category.id,
                price=pdata["price"],
                description=pdata["description"],
                status=EntityStatus.ACTIVE,
            )
            db.session.add(product)
            db.session.flush()

            # Thêm ảnh sản phẩm
            for idx, img in enumerate(pdata.get("images", [])):
                p_img = ProductImage(
                    product_id=product.id,
                    url=img["url"],
                    is_primary=img.get("is_primary", idx == 0),
                    sort_order=idx
                )
                db.session.add(p_img)

            # Tự động sinh tổ hợp biến thể (Size x Color)
            variants_created_for_prod = 0
            for s_name in pdata["sizes"]:
                for c_name in pdata["colors"]:
                    size_obj = sizes.get(s_name)
                    color_obj = colors.get(c_name)
                    if not size_obj or not color_obj:
                        continue

                    # Mã SKU chuẩn e-commerce: [SLUG]-[SIZE]-[COLOR]
                    sku_clean = f"{product.slug[:12].upper()}-{s_name.upper()}-{color_obj.id}"
                    variant = ProductVariant(
                        product_id=product.id,
                        size_id=size_obj.id,
                        color_id=color_obj.id,
                        sku=sku_clean,
                        stock_quantity=pdata["stock_per_variant"],
                        reserved_quantity=0,
                        status=EntityStatus.ACTIVE,
                    )
                    db.session.add(variant)
                    variants_created_for_prod += 1

            total_variants += variants_created_for_prod
            created_count += 1
            print(f"[✓] ĐÃ TẠO: {product.name} ({variants_created_for_prod} biến thể)")

        # Cập nhật luôn ảnh mặc định cho các sản phẩm chưa có ảnh
        all_products = db.session.scalars(db.select(Product)).all()
        for p in all_products:
            has_img = db.session.scalar(db.select(ProductImage).filter_by(product_id=p.id))
            if not has_img:
                db.session.add(ProductImage(
                    product_id=p.id,
                    url="img/placeholder.svg",
                    is_primary=True,
                    sort_order=0
                ))
                print(f"[+] Gán ảnh mặc định cho sản phẩm cũ: {p.name}")

        db.session.commit()
        print("=" * 60)
        print(f"HOÀN TẤT! Tạo mới: {created_count} | Cập nhật ảnh: {updated_img_count} | Biến thể: {total_variants}")
        print("=" * 60)


if __name__ == "__main__":
    run_import()
