"""
Script tạo dữ liệu mẫu cho toàn bộ hệ thống
Chạy: python manage.py shell < seed_data.py
"""
from finance.models import FinanceCategory, CashBook, Receipt, ReceiptItem, Payment
from orders.models import (
    Quotation, QuotationItem, Order, OrderItem, OrderReturn, OrderReturnItem, Packaging
)
from products.models import (
    Supplier, ProductCategory, Warehouse, Product, ProductStock,
    PurchaseOrder, PurchaseOrderItem, GoodsReceipt, GoodsReceiptItem,
    StockCheck, StockCheckItem, StockTransfer, StockTransferItem, CostAdjustment
)
from customers.models import Customer, CustomerGroup
import random
from django.utils import timezone
from datetime import date, timedelta
from django.contrib.auth.models import User
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()


print("=" * 60)
print("🚀 Bắt đầu tạo dữ liệu mẫu...")
print("=" * 60)

# ==================== USER ====================
admin_user = User.objects.filter(is_superuser=True).first()
if not admin_user:
    admin_user = User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print("✅ Tạo user admin")

staff1, _ = User.objects.get_or_create(username='nhanvien1', defaults={
    'first_name': 'Nguyễn Văn', 'last_name': 'An', 'email': 'an@company.com',
    'is_staff': True
})
staff1.set_password('123456')
staff1.save()

staff2, _ = User.objects.get_or_create(username='nhanvien2', defaults={
    'first_name': 'Trần Thị', 'last_name': 'Bình', 'email': 'binh@company.com',
    'is_staff': True
})
staff2.set_password('123456')
staff2.save()
print("✅ Tạo 2 nhân viên")

# ==================== NHÓM KHÁCH HÀNG ====================
group_data = [
    {'name': 'Khách VIP', 'description': 'Khách hàng thân thiết, mua hàng thường xuyên', 'discount_percent': 10},
    {'name': 'Khách sỉ', 'description': 'Đại lý, mua số lượng lớn', 'discount_percent': 15},
    {'name': 'Khách lẻ', 'description': 'Khách mua lẻ', 'discount_percent': 0},
    {'name': 'Đối tác', 'description': 'Đối tác kinh doanh', 'discount_percent': 5},
]
groups = []
for g in group_data:
    obj, _ = CustomerGroup.objects.get_or_create(name=g['name'], defaults=g)
    groups.append(obj)
print(f"✅ Tạo {len(groups)} nhóm khách hàng")

# ==================== KHÁCH HÀNG ====================
customer_data = [
    {'code': 'KH001', 'name': 'Công ty TNHH ABC', 'phone': '0901234567', 'email': 'abc@gmail.com',
     'address': '123 Nguyễn Huệ, Q.1, TP.HCM', 'company': 'Công ty TNHH ABC', 'tax_code': '0312345678'},
    {'code': 'KH002', 'name': 'Nguyễn Văn Tùng', 'phone': '0912345678', 'email': 'tung@gmail.com',
     'address': '456 Lê Lợi, Q.3, TP.HCM', 'company': ''},
    {'code': 'KH003', 'name': 'Trần Minh Đức', 'phone': '0923456789', 'email': 'duc@gmail.com',
     'address': '789 Trần Hưng Đạo, Q.5, TP.HCM'},
    {'code': 'KH004', 'name': 'Công ty CP XYZ', 'phone': '02812345678', 'email': 'info@xyz.vn',
     'address': '321 Điện Biên Phủ, Q.Bình Thạnh, TP.HCM', 'company': 'Công ty CP XYZ', 'tax_code': '0398765432'},
    {'code': 'KH005', 'name': 'Lê Thị Hương', 'phone': '0934567890', 'email': 'huong@gmail.com',
     'address': '55 Pasteur, Q.1, TP.HCM'},
    {'code': 'KH006', 'name': 'Phạm Quốc Bảo', 'phone': '0945678901', 'email': 'bao@gmail.com',
     'address': '67 CMT8, Q.Tân Bình, TP.HCM'},
    {'code': 'KH007', 'name': 'Đại lý Thành Công', 'phone': '0956789012', 'email': 'tc@gmail.com',
     'address': '89 Quang Trung, Q.Gò Vấp, TP.HCM', 'company': 'Đại lý Thành Công'},
    {'code': 'KH008', 'name': 'Shop Mỹ Phẩm Lan', 'phone': '0967890123', 'email': 'lan@gmail.com',
     'address': '12 Hai Bà Trưng, Q.1, TP.HCM'},
]
customers = []
for i, c in enumerate(customer_data):
    c['group'] = groups[i % len(groups)]
    c['created_by'] = admin_user
    c['total_purchased'] = random.randint(5000000, 200000000)
    c['total_debt'] = random.randint(0, 20000000)
    obj, _ = Customer.objects.get_or_create(code=c['code'], defaults=c)
    customers.append(obj)
print(f"✅ Tạo {len(customers)} khách hàng")

# ==================== NHÀ CUNG CẤP ====================
supplier_data = [
    {'code': 'NCC001', 'name': 'Công ty Phát Đạt', 'phone': '0281234567', 'email': 'phatdat@gmail.com',
     'address': '100 Nguyễn Văn Cừ, Q.5, TP.HCM', 'tax_code': '0301234567', 'contact_person': 'Anh Phát'},
    {'code': 'NCC002', 'name': 'Nhà phân phối Hòa Bình', 'phone': '0282345678', 'email': 'hoabinh@gmail.com',
     'address': '200 Lý Thường Kiệt, Q.10, TP.HCM', 'tax_code': '0302345678', 'contact_person': 'Chị Bình'},
    {'code': 'NCC003', 'name': 'Xưởng sản xuất Minh Tâm', 'phone': '0283456789', 'email': 'minhtam@gmail.com',
     'address': 'KCN Tân Tạo, Q.Bình Tân, TP.HCM', 'tax_code': '0303456789', 'contact_person': 'Anh Tâm'},
    {'code': 'NCC004', 'name': 'Công ty TNHH Việt Tiến', 'phone': '0284567890', 'email': 'viettien@gmail.com',
     'address': '500 Cách Mạng Tháng 8, Q.3, TP.HCM', 'tax_code': '0304567890', 'contact_person': 'Anh Tiến'},
    {'code': 'NCC005', 'name': 'Đại lý Thanh Xuân', 'phone': '0285678901', 'email': 'thanhxuan@gmail.com',
     'address': '88 Phan Xích Long, Q.Phú Nhuận, TP.HCM', 'contact_person': 'Chị Xuân'},
]
suppliers = []
for s in supplier_data:
    s['created_by'] = admin_user
    obj, _ = Supplier.objects.get_or_create(code=s['code'], defaults=s)
    suppliers.append(obj)
print(f"✅ Tạo {len(suppliers)} nhà cung cấp")

# ==================== DANH MỤC SẢN PHẨM ====================
cat_data = [
    {'name': 'Điện thoại', 'description': 'Điện thoại di động các loại'},
    {'name': 'Phụ kiện điện thoại', 'description': 'Ốp lưng, cáp sạc, tai nghe...'},
    {'name': 'Laptop', 'description': 'Máy tính xách tay'},
    {'name': 'Phụ kiện máy tính', 'description': 'Chuột, bàn phím, loa...'},
    {'name': 'Tablet', 'description': 'Máy tính bảng'},
    {'name': 'Đồng hồ thông minh', 'description': 'Smartwatch các loại'},
]
categories = []
for c in cat_data:
    obj, _ = ProductCategory.objects.get_or_create(name=c['name'], defaults=c)
    categories.append(obj)
print(f"✅ Tạo {len(categories)} danh mục sản phẩm")

# ==================== KHO ====================
wh_data = [
    {'code': 'KHO01', 'name': 'Kho chính HCM', 'address': 'Lô A1, KCN Tân Bình, TP.HCM', 'manager': admin_user},
    {'code': 'KHO02', 'name': 'Kho phụ Gò Vấp', 'address': '123 Nguyễn Oanh, Q.Gò Vấp, TP.HCM', 'manager': staff1},
    {'code': 'KHO03', 'name': 'Kho Hà Nội', 'address': '45 Hoàng Quốc Việt, Cầu Giấy, HN', 'manager': staff2},
]
warehouses = []
for w in wh_data:
    obj, _ = Warehouse.objects.get_or_create(code=w['code'], defaults=w)
    warehouses.append(obj)
print(f"✅ Tạo {len(warehouses)} kho")

# ==================== SẢN PHẨM ====================
product_data = [
    {'code': 'SP001', 'name': 'iPhone 15 Pro Max 256GB', 'category': categories[0], 'supplier': suppliers[0],
     'unit': 'Cái', 'cost_price': 28000000, 'listed_price': 34990000, 'selling_price': 33490000,
     'barcode': '8901234567890', 'description': 'iPhone 15 Pro Max 256GB chính hãng VN/A', 'min_stock': 5, 'max_stock': 50},
    {'code': 'SP002', 'name': 'Samsung Galaxy S24 Ultra', 'category': categories[0], 'supplier': suppliers[0],
     'unit': 'Cái', 'cost_price': 25000000, 'listed_price': 33990000, 'selling_price': 31990000,
     'barcode': '8901234567891', 'description': 'Samsung Galaxy S24 Ultra 256GB', 'min_stock': 5, 'max_stock': 50},
    {'code': 'SP003', 'name': 'Ốp lưng iPhone 15 Pro Max', 'category': categories[1], 'supplier': suppliers[1],
     'unit': 'Cái', 'cost_price': 50000, 'listed_price': 150000, 'selling_price': 120000,
     'description': 'Ốp lưng silicon trong suốt', 'min_stock': 20, 'max_stock': 200},
    {'code': 'SP004', 'name': 'Cáp sạc Type-C 1m', 'category': categories[1], 'supplier': suppliers[1],
     'unit': 'Cái', 'cost_price': 30000, 'listed_price': 99000, 'selling_price': 79000,
     'description': 'Cáp sạc nhanh 65W USB-C', 'min_stock': 30, 'max_stock': 500},
    {'code': 'SP005', 'name': 'MacBook Pro M3 14"', 'category': categories[2], 'supplier': suppliers[2],
     'unit': 'Cái', 'cost_price': 42000000, 'listed_price': 52990000, 'selling_price': 49990000,
     'barcode': '8901234567892', 'description': 'MacBook Pro 14 inch chip M3 16GB/512GB', 'min_stock': 3, 'max_stock': 20},
    {'code': 'SP006', 'name': 'Laptop Dell XPS 15', 'category': categories[2], 'supplier': suppliers[2],
     'unit': 'Cái', 'cost_price': 32000000, 'listed_price': 42990000, 'selling_price': 39990000,
     'description': 'Dell XPS 15 i7-13700H 16GB/512GB', 'min_stock': 3, 'max_stock': 20},
    {'code': 'SP007', 'name': 'Chuột Logitech MX Master 3S', 'category': categories[3], 'supplier': suppliers[3],
     'unit': 'Cái', 'cost_price': 1500000, 'listed_price': 2490000, 'selling_price': 2190000,
     'description': 'Chuột không dây cao cấp', 'min_stock': 10, 'max_stock': 100},
    {'code': 'SP008', 'name': 'Bàn phím cơ Keychron K8', 'category': categories[3], 'supplier': suppliers[3],
     'unit': 'Cái', 'cost_price': 1800000, 'listed_price': 2790000, 'selling_price': 2490000,
     'description': 'Bàn phím cơ wireless Gateron Brown', 'min_stock': 10, 'max_stock': 100},
    {'code': 'SP009', 'name': 'iPad Air M2 11"', 'category': categories[4], 'supplier': suppliers[0],
     'unit': 'Cái', 'cost_price': 14000000, 'listed_price': 18990000, 'selling_price': 17490000,
     'description': 'iPad Air M2 256GB WiFi', 'min_stock': 5, 'max_stock': 30},
    {'code': 'SP010', 'name': 'Apple Watch Series 9', 'category': categories[5], 'supplier': suppliers[0],
     'unit': 'Cái', 'cost_price': 8000000, 'listed_price': 11990000, 'selling_price': 10990000,
     'description': 'Apple Watch Series 9 45mm GPS', 'min_stock': 5, 'max_stock': 30},
    {'code': 'SP011', 'name': 'Tai nghe AirPods Pro 2', 'category': categories[1], 'supplier': suppliers[0],
     'unit': 'Cái', 'cost_price': 4500000, 'listed_price': 6790000, 'selling_price': 5990000,
     'description': 'AirPods Pro 2 USB-C chống ồn', 'min_stock': 10, 'max_stock': 100},
    {'code': 'SP012', 'name': 'Sạc nhanh 65W GaN', 'category': categories[1], 'supplier': suppliers[4],
     'unit': 'Cái', 'cost_price': 200000, 'listed_price': 450000, 'selling_price': 390000,
     'description': 'Củ sạc nhanh 65W GaN 3 cổng', 'min_stock': 20, 'max_stock': 300},
]
products = []
for p in product_data:
    p['created_by'] = admin_user
    obj, _ = Product.objects.get_or_create(code=p['code'], defaults=p)
    products.append(obj)
print(f"✅ Tạo {len(products)} sản phẩm")

# ==================== TỒN KHO ====================
for prod in products:
    for wh in warehouses:
        qty = random.randint(5, 100)
        ProductStock.objects.get_or_create(
            product=prod, warehouse=wh,
            defaults={'quantity': qty}
        )
print(f"✅ Tạo tồn kho cho {len(products)} SP x {len(warehouses)} kho")

# ==================== ĐƠN ĐẶT HÀNG NHẬP ====================
today = date.today()
po_list = []
for i in range(5):
    po_date = today - timedelta(days=random.randint(10, 60))
    sup = suppliers[i % len(suppliers)]
    wh = warehouses[i % len(warehouses)]
    po, created = PurchaseOrder.objects.get_or_create(
        code=f'PO{(i + 1):04d}',
        defaults={
            'supplier': sup, 'warehouse': wh, 'status': random.choice([0, 1, 2, 3]),
            'order_date': po_date, 'expected_date': po_date + timedelta(days=7),
            'note': f'Đơn đặt hàng nhập #{i + 1}', 'created_by': admin_user, 'total_amount': 0,
        }
    )
    if created:
        total = 0
        prods_sample = random.sample(products, min(3, len(products)))
        for prod in prods_sample:
            qty = random.randint(10, 50)
            price = float(prod.cost_price)
            PurchaseOrderItem.objects.create(
                purchase_order=po, product=prod, quantity=qty,
                unit_price=price, total_price=qty * price
            )
            total += qty * price
        po.total_amount = total
        po.save()
    po_list.append(po)
print(f"✅ Tạo {len(po_list)} đơn đặt hàng nhập")

# ==================== PHIẾU NHẬP KHO ====================
gr_list = []
for i in range(4):
    gr_date = today - timedelta(days=random.randint(5, 40))
    sup = suppliers[i % len(suppliers)]
    wh = warehouses[i % len(warehouses)]
    gr, created = GoodsReceipt.objects.get_or_create(
        code=f'NK{(i + 1):04d}',
        defaults={
            'supplier': sup, 'warehouse': wh, 'status': random.choice([0, 1]),
            'receipt_date': gr_date, 'note': f'Phiếu nhập kho #{i + 1}',
            'created_by': admin_user, 'total_amount': 0,
        }
    )
    if created:
        total = 0
        prods_sample = random.sample(products, min(3, len(products)))
        for prod in prods_sample:
            qty = random.randint(5, 30)
            price = float(prod.cost_price)
            GoodsReceiptItem.objects.create(
                goods_receipt=gr, product=prod, quantity=qty,
                unit_price=price, total_price=qty * price
            )
            total += qty * price
        gr.total_amount = total
        gr.save()
    gr_list.append(gr)
print(f"✅ Tạo {len(gr_list)} phiếu nhập kho")

# ==================== KIỂM KHO ====================
for i in range(3):
    sc_date = today - timedelta(days=random.randint(1, 30))
    wh = warehouses[i % len(warehouses)]
    sc, created = StockCheck.objects.get_or_create(
        code=f'KK{(i + 1):04d}',
        defaults={
            'warehouse': wh, 'status': random.choice([0, 1]),
            'check_date': sc_date, 'note': f'Kiểm kê tháng {sc_date.month}',
            'created_by': admin_user,
        }
    )
    if created:
        prods_sample = random.sample(products, min(4, len(products)))
        for prod in prods_sample:
            sys_qty = random.randint(10, 50)
            actual_qty = sys_qty + random.randint(-5, 5)
            StockCheckItem.objects.create(
                stock_check=sc, product=prod,
                system_quantity=sys_qty, actual_quantity=actual_qty,
                difference=actual_qty - sys_qty,
            )
print("✅ Tạo 3 phiếu kiểm kê")

# ==================== CHUYỂN KHO ====================
for i in range(3):
    st_date = today - timedelta(days=random.randint(1, 20))
    from_wh = warehouses[i % len(warehouses)]
    to_wh = warehouses[(i + 1) % len(warehouses)]
    st, created = StockTransfer.objects.get_or_create(
        code=f'CK{(i + 1):04d}',
        defaults={
            'from_warehouse': from_wh, 'to_warehouse': to_wh,
            'status': random.choice([0, 1, 2]),
            'transfer_date': st_date, 'note': f'Chuyển kho #{i + 1}',
            'created_by': admin_user,
        }
    )
    if created:
        prods_sample = random.sample(products, min(3, len(products)))
        for prod in prods_sample:
            StockTransferItem.objects.create(
                transfer=st, product=prod, quantity=random.randint(5, 20)
            )
print("✅ Tạo 3 phiếu chuyển kho")

# ==================== ĐIỀU CHỈNH GIÁ VỐN ====================
for i in range(3):
    prod = products[i]
    old_cost = float(prod.cost_price)
    new_cost = old_cost * random.uniform(0.9, 1.15)
    CostAdjustment.objects.create(
        product=prod, old_cost=old_cost, new_cost=int(new_cost),
        reason=f'Điều chỉnh giá vốn theo thị trường tháng {today.month}',
        adjusted_by=admin_user,
    )
print("✅ Tạo 3 điều chỉnh giá vốn")

# ==================== DANH MỤC THU CHI ====================
fin_cat_data = [
    {'name': 'Bán hàng', 'type': 1, 'description': 'Thu từ bán hàng sản phẩm'},
    {'name': 'Thu công nợ', 'type': 1, 'description': 'Thu tiền công nợ khách hàng'},
    {'name': 'Thu khác', 'type': 1, 'description': 'Các khoản thu khác'},
    {'name': 'Nhập hàng', 'type': 2, 'description': 'Chi mua hàng nhập kho'},
    {'name': 'Lương nhân viên', 'type': 2, 'description': 'Chi trả lương hàng tháng'},
    {'name': 'Chi phí vận chuyển', 'type': 2, 'description': 'Phí giao hàng, vận chuyển'},
    {'name': 'Chi phí mặt bằng', 'type': 2, 'description': 'Tiền thuê mặt bằng, điện nước'},
    {'name': 'Chi khác', 'type': 2, 'description': 'Các khoản chi khác'},
]
fin_cats = []
for fc in fin_cat_data:
    obj, _ = FinanceCategory.objects.get_or_create(name=fc['name'], defaults=fc)
    fin_cats.append(obj)
print(f"✅ Tạo {len(fin_cats)} danh mục thu chi")

# ==================== QUỸ ====================
cb_data = [
    {'name': 'Quỹ tiền mặt', 'description': 'Quỹ tiền mặt tại cửa hàng', 'balance': 50000000},
    {'name': 'Ngân hàng Vietcombank', 'description': 'TK 0071234567890 - VCB', 'balance': 200000000},
    {'name': 'Ngân hàng Techcombank', 'description': 'TK 19012345678901 - TCB', 'balance': 150000000},
]
cashbooks = []
for cb in cb_data:
    obj, _ = CashBook.objects.get_or_create(name=cb['name'], defaults=cb)
    cashbooks.append(obj)
print(f"✅ Tạo {len(cashbooks)} quỹ")

# ==================== BÁO GIÁ ====================
quote_list = []
for i in range(5):
    q_date = today - timedelta(days=random.randint(5, 45))
    cust = customers[i % len(customers)]
    q, created = Quotation.objects.get_or_create(
        code=f'BG{(i + 1):04d}',
        defaults={
            'customer': cust, 'status': random.choice([0, 1, 2]),
            'quotation_date': q_date, 'valid_until': q_date + timedelta(days=30),
            'discount_amount': random.choice([0, 500000, 1000000]),
            'note': f'Báo giá cho {cust.name}',
            'created_by': admin_user, 'total_amount': 0, 'final_amount': 0,
        }
    )
    if created:
        total = 0
        prods_sample = random.sample(products, random.randint(2, 4))
        for prod in prods_sample:
            qty = random.randint(1, 10)
            price = float(prod.selling_price)
            line_total = qty * price
            total += line_total
            QuotationItem.objects.create(
                quotation=q, product=prod, quantity=qty,
                unit_price=price, total_price=line_total,
            )
        q.total_amount = total
        q.final_amount = total - float(q.discount_amount)
        q.save()
    quote_list.append(q)
print(f"✅ Tạo {len(quote_list)} báo giá")

# ==================== ĐƠN HÀNG ====================
order_list = []
for i in range(8):
    o_date = today - timedelta(days=random.randint(1, 50))
    cust = customers[i % len(customers)]
    wh = warehouses[i % len(warehouses)]
    status = random.choice([0, 1, 2, 3, 5])
    o, created = Order.objects.get_or_create(
        code=f'DH{(i + 1):04d}',
        defaults={
            'customer': cust, 'warehouse': wh,
            'status': status,
            'payment_status': random.choice([0, 1, 2]),
            'order_date': o_date,
            'discount_amount': random.choice([0, 200000, 500000]),
            'note': f'Đơn hàng #{i + 1} - {cust.name}',
            'created_by': admin_user,
            'total_amount': 0, 'final_amount': 0, 'paid_amount': 0,
        }
    )
    if created:
        total = 0
        prods_sample = random.sample(products, random.randint(1, 5))
        for prod in prods_sample:
            qty = random.randint(1, 5)
            price = float(prod.selling_price)
            line_total = qty * price
            total += line_total
            OrderItem.objects.create(
                order=o, product=prod, quantity=qty,
                unit_price=price, cost_price=float(prod.cost_price),
                total_price=line_total,
                is_below_listed=(price < float(prod.listed_price)),
            )
        o.total_amount = total
        o.final_amount = total - float(o.discount_amount)
        o.paid_amount = float(o.final_amount) * random.choice([0, 0.5, 1.0])
        o.save()
    order_list.append(o)
print(f"✅ Tạo {len(order_list)} đơn hàng")

# ==================== TRẢ HÀNG ====================
for i in range(3):
    r_date = today - timedelta(days=random.randint(1, 20))
    cust = customers[i]
    ret, created = OrderReturn.objects.get_or_create(
        code=f'TH{(i + 1):04d}',
        defaults={
            'order': order_list[i] if i < len(order_list) else None,
            'customer': cust, 'warehouse': warehouses[0],
            'status': random.choice([0, 1, 2]),
            'return_date': r_date,
            'total_refund': random.randint(500000, 10000000),
            'reason': random.choice(['Hàng lỗi', 'Sai sản phẩm', 'Khách đổi ý']),
            'created_by': admin_user,
        }
    )
    if created:
        prod = products[i]
        OrderReturnItem.objects.create(
            order_return=ret, product=prod, quantity=1,
            unit_price=float(prod.selling_price), total_price=float(prod.selling_price),
            reason='Hàng lỗi từ nhà sản xuất',
        )
print("✅ Tạo 3 phiếu trả hàng")

# ==================== ĐÓNG GÓI ====================
for i in range(4):
    if i < len(order_list):
        Packaging.objects.get_or_create(
            code=f'DG{(i + 1):04d}',
            defaults={
                'order': order_list[i],
                'status': random.choice([0, 1, 2]),
                'weight': round(random.uniform(0.5, 15.0), 2),
                'packed_by': staff1,
                'packed_at': timezone.now() - timedelta(hours=random.randint(1, 72)),
                'note': f'Đóng gói đơn hàng {order_list[i].code}',
            }
        )
print("✅ Tạo 4 phiếu đóng gói")

# ==================== PHIẾU THU ====================
# Phiếu thu bán hàng (có sản phẩm)
sale_cat = fin_cats[0]  # Bán hàng
for i in range(4):
    r_date = today - timedelta(days=random.randint(1, 30))
    cust = customers[i % len(customers)]
    cb = cashbooks[i % len(cashbooks)]
    receipt, created = Receipt.objects.get_or_create(
        code=f'PT{(i + 1):04d}',
        defaults={
            'category': sale_cat, 'cash_book': cb, 'customer': cust,
            'receipt_date': r_date, 'status': 1,
            'description': f'Thu tiền bán hàng - {cust.name}',
            'created_by': admin_user, 'amount': 0,
        }
    )
    if created:
        total = 0
        prods_sample = random.sample(products, random.randint(1, 3))
        for prod in prods_sample:
            qty = random.randint(1, 5)
            price = float(prod.selling_price)
            line_total = qty * price
            total += line_total
            ReceiptItem.objects.create(
                receipt=receipt, product=prod, quantity=qty,
                unit_price=price, total_price=line_total,
            )
        receipt.amount = total
        receipt.save()

# Phiếu thu công nợ (không có sản phẩm)
debt_cat = fin_cats[1]  # Thu công nợ
for i in range(3):
    r_date = today - timedelta(days=random.randint(1, 25))
    cust = customers[(i + 4) % len(customers)]
    cb = cashbooks[i % len(cashbooks)]
    Receipt.objects.get_or_create(
        code=f'PT{(i + 5):04d}',
        defaults={
            'category': debt_cat, 'cash_book': cb, 'customer': cust,
            'receipt_date': r_date, 'status': 1,
            'amount': random.randint(5000000, 50000000),
            'description': f'Thu công nợ tháng {r_date.month} - {cust.name}',
            'created_by': admin_user,
        }
    )
print("✅ Tạo 7 phiếu thu (4 bán hàng + 3 công nợ)")

# ==================== PHIẾU CHI ====================
pay_data = [
    {'cat_idx': 3, 'desc': 'Thanh toán nhập hàng NCC Phát Đạt', 'amount': 85000000},
    {'cat_idx': 3, 'desc': 'Thanh toán nhập hàng NCC Hòa Bình', 'amount': 45000000},
    {'cat_idx': 4, 'desc': 'Lương tháng 02/2026', 'amount': 120000000},
    {'cat_idx': 4, 'desc': 'Lương tháng 01/2026', 'amount': 115000000},
    {'cat_idx': 5, 'desc': 'Phí giao hàng GHTK tháng 02', 'amount': 8500000},
    {'cat_idx': 6, 'desc': 'Tiền thuê mặt bằng Q1 2026', 'amount': 45000000},
    {'cat_idx': 6, 'desc': 'Tiền điện nước tháng 02', 'amount': 12000000},
    {'cat_idx': 7, 'desc': 'Chi phí marketing Facebook Ads', 'amount': 15000000},
]
for i, pd in enumerate(pay_data):
    p_date = today - timedelta(days=random.randint(1, 45))
    cb = cashbooks[i % len(cashbooks)]
    Payment.objects.get_or_create(
        code=f'PC{(i + 1):04d}',
        defaults={
            'category': fin_cats[pd['cat_idx']],
            'cash_book': cb, 'payment_date': p_date, 'status': 1,
            'amount': pd['amount'], 'description': pd['desc'],
            'created_by': admin_user,
        }
    )
print(f"✅ Tạo {len(pay_data)} phiếu chi")

# ==================== TỔNG KẾT ====================
print("\n" + "=" * 60)
print("🎉 HOÀN THÀNH TẠO DỮ LIỆU MẪU!")
print("=" * 60)
print(f"""
📊 Tổng kết:
  👥 Nhân viên:           {User.objects.count()}
  👥 Nhóm KH:             {CustomerGroup.objects.count()}
  👥 Khách hàng:           {Customer.objects.count()}
  🏭 Nhà cung cấp:        {Supplier.objects.count()}
  📂 Danh mục SP:          {ProductCategory.objects.count()}
  🏪 Kho:                  {Warehouse.objects.count()}
  📦 Sản phẩm:             {Product.objects.count()}
  📋 Tồn kho:              {ProductStock.objects.count()}
  📝 Đơn đặt hàng nhập:   {PurchaseOrder.objects.count()}
  📥 Phiếu nhập kho:      {GoodsReceipt.objects.count()}
  🔍 Phiếu kiểm kê:       {StockCheck.objects.count()}
  🔄 Phiếu chuyển kho:    {StockTransfer.objects.count()}
  💰 Điều chỉnh giá:      {CostAdjustment.objects.count()}
  📋 Báo giá:              {Quotation.objects.count()}
  🛒 Đơn hàng:             {Order.objects.count()}
  ↩️  Trả hàng:            {OrderReturn.objects.count()}
  📦 Đóng gói:             {Packaging.objects.count()}
  💵 Danh mục thu chi:     {FinanceCategory.objects.count()}
  🏦 Quỹ:                  {CashBook.objects.count()}
  💰 Phiếu thu:            {Receipt.objects.count()}
  💸 Phiếu chi:            {Payment.objects.count()}
""")
