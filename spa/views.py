import json
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .models import Staff, Room, Service, ServiceCategory, Booking, BookingItem
from core.store_utils import filter_by_store, get_user_store

logger = logging.getLogger(__name__)


# ============ PAGES ============

@login_required(login_url="/login/")
def staff_tbl(request):
    return render(request, "spa/staff_list.html", {'active_tab': 'spa_staff_tbl'})


@login_required(login_url="/login/")
def room_tbl(request):
    return render(request, "spa/room_list.html", {'active_tab': 'spa_room_tbl'})


@login_required(login_url="/login/")
def service_tbl(request):
    categories = list(ServiceCategory.objects.filter(is_active=True).values('id', 'name'))
    return render(request, "spa/service_list.html", {'active_tab': 'spa_service_tbl', 'categories': categories})


@login_required(login_url="/login/")
def booking_tbl(request):
    return render(request, "spa/booking_list.html", {'active_tab': 'spa_booking_tbl'})


@login_required(login_url="/login/")
def booking_calendar(request):
    return render(request, "spa/booking_calendar.html", {'active_tab': 'spa_booking_calendar'})


# ============ API: STAFF ============

@login_required(login_url="/login/")
def api_get_staff(request):
    staff = Staff.objects.all()
    data = [{
        'id': s.id, 'code': s.code, 'name': s.name,
        'phone': s.phone or '', 'position': s.position,
        'position_display': s.get_position_display(),
        'commission_rate': float(s.commission_rate),
        'avatar': s.avatar.url if s.avatar else '',
        'note': s.note or '', 'is_active': s.is_active,
    } for s in staff]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_staff(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        sid = data.get('id')
        s = Staff.objects.get(id=sid) if sid else Staff()
        s.code = data.get('code', '')
        s.name = data.get('name', '')
        s.phone = data.get('phone', '')
        s.position = data.get('position', 1)
        s.commission_rate = data.get('commission_rate', 0) or 0
        s.note = data.get('note', '')
        s.is_active = data.get('is_active', True)
        s.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_staff(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        Staff.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: ROOM ============

@login_required(login_url="/login/")
def api_get_rooms(request):
    rooms = Room.objects.all()
    data = [{
        'id': r.id, 'name': r.name,
        'room_type': r.room_type, 'room_type_display': r.get_room_type_display(),
        'status': r.status, 'status_display': r.get_status_display(),
        'max_capacity': r.max_capacity, 'note': r.note or '',
        'is_active': r.is_active,
    } for r in rooms]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_room(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        rid = data.get('id')
        r = Room.objects.get(id=rid) if rid else Room()
        r.name = data.get('name', '')
        r.room_type = data.get('room_type', 1)
        r.status = data.get('status', 0)
        r.max_capacity = data.get('max_capacity', 1)
        r.note = data.get('note', '')
        r.is_active = data.get('is_active', True)
        r.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_room(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        Room.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: SERVICE ============

@login_required(login_url="/login/")
def api_get_services(request):
    services = Service.objects.select_related('category').all()
    data = [{
        'id': s.id, 'code': s.code, 'name': s.name,
        'category': s.category.name if s.category else '',
        'category_id': s.category_id,
        'duration_minutes': s.duration_minutes,
        'price': float(s.price),
        'commission_rate': float(s.commission_rate),
        'description': s.description or '',
        'image': s.image.url if s.image else '',
        'is_active': s.is_active,
    } for s in services]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_service(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        sid = data.get('id')
        s = Service.objects.get(id=sid) if sid else Service()
        s.code = data.get('code', '')
        s.name = data.get('name', '')
        s.category_id = data.get('category_id') or None
        s.duration_minutes = data.get('duration_minutes', 60)
        s.price = data.get('price', 0) or 0
        s.commission_rate = data.get('commission_rate', 0) or 0
        s.description = data.get('description', '')
        s.is_active = data.get('is_active', True)
        s.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_service(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        Service.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_get_service_categories(request):
    cats = ServiceCategory.objects.all()
    data = [{'id': c.id, 'name': c.name, 'description': c.description or '', 'is_active': c.is_active} for c in cats]
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_service_category(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        cid = data.get('id')
        c = ServiceCategory.objects.get(id=cid) if cid else ServiceCategory()
        c.name = data.get('name', '')
        c.description = data.get('description', '')
        c.save()
        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


# ============ API: BOOKING ============

@login_required(login_url="/login/")
def api_get_bookings(request):
    date_from = request.GET.get('from_date')
    date_to = request.GET.get('to_date')
    status = request.GET.get('status')

    bookings = Booking.objects.select_related('customer', 'staff', 'room').prefetch_related('items__service', 'items__staff')
    bookings = filter_by_store(bookings, request)

    if date_from:
        bookings = bookings.filter(booking_date__gte=date_from)
    if date_to:
        bookings = bookings.filter(booking_date__lte=date_to)
    if status is not None and status != '':
        bookings = bookings.filter(status=int(status))

    data = []
    for b in bookings:
        items = [{
            'id': it.id,
            'service_id': it.service_id,
            'service_name': it.service.name if it.service else '',
            'service_code': it.service.code if it.service else '',
            'staff_id': it.staff_id,
            'staff_name': it.staff.name if it.staff else '',
            'quantity': it.quantity,
            'unit_price': float(it.unit_price),
            'total_price': float(it.total_price),
            'commission_amount': float(it.commission_amount),
        } for it in b.items.all()]

        cust_name = b.customer.name if b.customer else (b.customer_name or 'Khách vãng lai')
        cust_phone = b.customer.phone if b.customer else (b.customer_phone or '')

        data.append({
            'id': b.id, 'code': b.code,
            'customer_id': b.customer_id,
            'customer_name': cust_name,
            'customer_phone': cust_phone,
            'staff_id': b.staff_id,
            'staff_name': b.staff.name if b.staff else '',
            'room_id': b.room_id,
            'room_name': b.room.name if b.room else '',
            'booking_date': b.booking_date.strftime('%Y-%m-%d') if b.booking_date else '',
            'booking_date_display': b.booking_date.strftime('%d/%m/%Y') if b.booking_date else '',
            'start_time': b.start_time.strftime('%H:%M') if b.start_time else '',
            'end_time': b.end_time.strftime('%H:%M') if b.end_time else '',
            'status': b.status,
            'status_display': b.get_status_display(),
            'total_amount': float(b.total_amount),
            'discount_amount': float(b.discount_amount),
            'final_amount': float(b.final_amount),
            'paid_amount': float(b.paid_amount),
            'commission_amount': float(b.commission_amount),
            'note': b.note or '',
            'items': items,
        })
    return JsonResponse({'data': data})


@login_required(login_url="/login/")
def api_save_booking(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        bid = data.get('id')
        b = Booking.objects.get(id=bid) if bid else Booking()
        if not bid:
            b.created_by = request.user

        b.code = data.get('code', '')
        # Auto-assign store
        user_store = get_user_store(request)
        if user_store:
            b.store = user_store
        b.customer_id = data.get('customer_id') or None
        b.customer_name = data.get('customer_name', '')
        b.customer_phone = data.get('customer_phone', '')
        b.staff_id = data.get('staff_id') or None
        b.room_id = data.get('room_id') or None
        b.booking_date = data.get('booking_date')
        b.start_time = data.get('start_time')
        b.end_time = data.get('end_time') or None
        b.status = data.get('status', 0)
        b.discount_amount = data.get('discount_amount', 0) or 0
        b.note = data.get('note', '')

        # Calculate items
        items_data = data.get('items', [])
        total = 0
        total_commission = 0
        for item in items_data:
            qty = int(item.get('quantity', 1))
            price = float(item.get('unit_price', 0))
            total += qty * price

            # Commission
            service = Service.objects.filter(id=item.get('service_id')).first()
            staff_item = Staff.objects.filter(id=item.get('staff_id')).first()
            comm_rate = 0
            if service and service.commission_rate > 0:
                comm_rate = float(service.commission_rate)
            elif staff_item and staff_item.commission_rate > 0:
                comm_rate = float(staff_item.commission_rate)
            elif b.staff and b.staff.commission_rate > 0:
                comm_rate = float(b.staff.commission_rate)
            item['_commission'] = qty * price * comm_rate / 100
            total_commission += item['_commission']

        b.total_amount = total
        b.final_amount = total - float(b.discount_amount)
        b.commission_amount = total_commission
        b.save()

        # Save items
        b.items.all().delete()
        for item in items_data:
            service_id = item.get('service_id')
            if not service_id:
                continue
            qty = int(item.get('quantity', 1))
            price = float(item.get('unit_price', 0))
            BookingItem.objects.create(
                booking=b,
                service_id=service_id,
                staff_id=item.get('staff_id') or None,
                quantity=qty,
                unit_price=price,
                total_price=qty * price,
                commission_amount=item.get('_commission', 0),
            )

        # Update room status
        if b.room:
            if b.status == 1:  # Đang phục vụ
                b.room.status = 1
            elif b.status in [2, 3]:  # Hoàn thành / Hủy
                b.room.status = 0
            b.room.save(update_fields=['status'])

        return JsonResponse({'status': 'ok', 'message': 'Lưu thành công'})
    except Exception as e:
        logger.error(f"Error saving booking: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_delete_booking(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'})
    try:
        data = json.loads(request.body)
        Booking.objects.filter(id=data.get('id')).delete()
        return JsonResponse({'status': 'ok', 'message': 'Xóa thành công'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)})


@login_required(login_url="/login/")
def api_generate_booking_code(request):
    today = datetime.now().strftime('%d%m')
    last = Booking.objects.filter(code__startswith=f'BK-{today}').order_by('-code').first()
    if last:
        try:
            num = int(last.code.split('-')[-1]) + 1
        except:
            num = 1
    else:
        num = 1
    code = f'BK-{today}-{num:03d}'
    return JsonResponse({'code': code})
