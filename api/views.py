import json
import bcrypt
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection, transaction
from django.db.models import Q, Count
from django.utils import timezone
from .models import (
    Hostel, Floor, Room, RoomBedsShare, Bed, Resident, Institute, SharingType, 
    ExitReason, Allocation, Renewal, Requirement, ConstructionPhase, User
)

def serialize_user(user):
    return {
        'id': user.id,
        'username': user.username,
        'full_name': user.full_name,
        'role': user.role,
        'hostel_id': user.hostel_id,
        'hostel_name': user.hostel.name if user.hostel else 'All Hostels'
    }

@csrf_exempt
def auth_login(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return JsonResponse({'status': 'error', 'message': 'Username and password required'}, status=400)
            
        user = User.objects.filter(username=username, is_active=True).first()
        if not user:
            return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)
            
        # Verify password using bcrypt
        password_bytes = password.encode('utf-8')
        hash_bytes = user.password_hash.encode('utf-8')
        
        if bcrypt.checkpw(password_bytes, hash_bytes):
            request.session['user_id'] = user.id
            return JsonResponse({'status': 'success', 'user': serialize_user(user)})
        else:
            return JsonResponse({'status': 'error', 'message': 'Invalid username or password'}, status=401)
            
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def dashboard_stats(request):
    try:
        hostels_count = Hostel.objects.count()
        rooms_count = Room.objects.count()
        
        total_capacity = sum(r.capacity for r in Room.objects.filter(is_active=True))
        active_allocations = Allocation.objects.filter(status='active').count()
        vacant_beds = max(0, total_capacity - active_allocations)
        pending_renewals = Renewal.objects.filter(renewal_status='TBR').count()
        
        hostel_stats = []
        with connection.cursor() as cursor:
            cursor.execute("SELECT hostel_id, hostel_name, gender, capacity, occupied, vacant FROM vw_hostel_occupancy ORDER BY hostel_name")
            rows = cursor.fetchall()
            for r in rows:
                hostel_stats.append({
                    'hostel_id': r[0],
                    'hostel_name': r[1],
                    'gender': r[2],
                    'capacity': r[3],
                    'occupied': r[4],
                    'vacant': r[5]
                })
                
        return JsonResponse({
            'status': 'success',
            'stats': {
                'hostels': hostels_count,
                'rooms': rooms_count,
                'capacity': total_capacity,
                'occupied': active_allocations,
                'vacant': vacant_beds,
                'pending_renewals': pending_renewals,
                'hostel_occupancy': hostel_stats
            }
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# ============================================================
# HOSTELS CRUD
# ============================================================
@csrf_exempt
def hostels_list(request):
    if request.method == 'GET':
        hostels = Hostel.objects.all().order_by('name')
        data = [{
            'id': h.id,
            'name': h.name,
            'gender': h.gender,
            'warden_name': h.warden_name,
            'warden_phone': h.warden_phone
        } for h in hostels]
        return JsonResponse({'status': 'success', 'data': data})

    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            h = Hostel.objects.create(
                name=data['name'],
                gender=data['gender'],
                warden_name=data.get('warden_name'),
                warden_phone=data.get('warden_phone')
            )
            floor_range = data.get('floor_range', '1-5')
            if floor_range:
                floors_to_create = []
                if '-' in str(floor_range):
                    parts = str(floor_range).split('-')
                    if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                        start_f = int(parts[0].strip())
                        end_f = int(parts[1].strip())
                        for f in range(start_f, end_f + 1):
                            floors_to_create.append(str(f))
                elif str(floor_range).isdigit():
                    for f in range(1, int(floor_range) + 1):
                        floors_to_create.append(str(f))
                
                for fl in floors_to_create:
                    Floor.objects.get_or_create(
                        hostel=h,
                        floor_number=fl,
                        defaults={'floor_name': f"Floor {fl}"}
                    )
            return JsonResponse({'status': 'success', 'id': h.id}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@csrf_exempt
def hostels_detail(request, hostel_id):
    try:
        hostel = Hostel.objects.get(id=hostel_id)
    except Hostel.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Hostel not found'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            hostel.name = data.get('name', hostel.name)
            hostel.gender = data.get('gender', hostel.gender)
            hostel.warden_name = data.get('warden_name', hostel.warden_name)
            hostel.warden_phone = data.get('warden_phone', hostel.warden_phone)
            hostel.save()
            return JsonResponse({'status': 'success', 'message': 'Hostel updated'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    elif request.method == 'DELETE':
        try:
            hostel.delete()
            return JsonResponse({'status': 'success', 'message': 'Hostel deleted'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)


# ============================================================
# ROOMS CRUD
# ============================================================
@csrf_exempt
def rooms_list(request):
    if request.method == 'GET':
        hostel_id = request.GET.get('hostel_id')
        rooms = Room.objects.all().select_related('hostel', 'sharing_type')
        if hostel_id:
            rooms = rooms.filter(hostel_id=hostel_id)
            
        rooms = rooms.order_by('hostel__name', 'room_number')
        
        occupancies = {}
        with connection.cursor() as cursor:
            cursor.execute("SELECT room_id, occupied, vacant FROM vw_room_occupancy")
            for r in cursor.fetchall():
                occupancies[r[0]] = {'occupied': r[1], 'vacant': r[2]}
                
        data = []
        for r in rooms:
            occ = occupancies.get(r.id, {'occupied': 0, 'vacant': r.capacity})
            data.append({
                'id': r.id,
                'room_number': r.room_number,
                'hostel_id': r.hostel_id,
                'hostel_name': r.hostel.name,
                'sharing_type_id': r.sharing_type_id,
                'sharing_type_label': r.sharing_type.label if r.sharing_type else 'Default',
                'floor': r.floor,
                'capacity': r.capacity,
                'is_active': r.is_active,
                'occupied': occ['occupied'],
                'vacant': occ['vacant']
            })
        return JsonResponse({'status': 'success', 'data': data})
        
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            hostel_id = data['hostel_id']
            floor_input = str(data.get('floor', '1')).strip()

            # Default sharing type if not explicitly passed
            sharing_type_id = data.get('sharing_type_id')
            if not sharing_type_id:
                st = SharingType.objects.first()
                if not st:
                    st = SharingType.objects.create(label='4 Sharing', bed_count=4, is_attached=True)
                sharing_type_id = st.id

            # Default capacity if not explicitly passed
            capacity = int(data.get('capacity', 4))

            # Determine list of floors to create
            floors_to_create = []
            if '-' in floor_input:
                parts = floor_input.split('-')
                if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                    start_f = int(parts[0].strip())
                    end_f = int(parts[1].strip())
                    for f in range(start_f, end_f + 1):
                        floors_to_create.append(str(f))
                else:
                    floors_to_create.append(floor_input)
            elif floor_input.isdigit() and int(floor_input) > 1 and not data.get('room_number'):
                for f in range(1, int(floor_input) + 1):
                    floors_to_create.append(str(f))
            else:
                floors_to_create.append(floor_input)

            is_floor_only = data.get('is_floor_only', False) or not data.get('room_number')

            created_ids = []
            for fl in floors_to_create:
                floor_obj, _ = Floor.objects.get_or_create(
                    hostel_id=hostel_id,
                    floor_number=fl,
                    defaults={'floor_name': f"Floor {fl}" if fl != 'Ground' else 'Ground Floor'}
                )

                if is_floor_only:
                    # Register floor placeholder without creating dummy rooms/beds
                    if not Room.objects.filter(hostel_id=hostel_id, floor=fl).exists():
                        r = Room.objects.create(
                            hostel_id=hostel_id,
                            floor_obj=floor_obj,
                            sharing_type_id=sharing_type_id,
                            room_number=f"F_{fl}_INIT",
                            floor=fl,
                            capacity=0,
                            is_active=True
                        )
                        created_ids.append(r.id)
                else:
                    custom_room_num = str(data.get('room_number', '')).strip()
                    rooms_to_create = []
                    if custom_room_num:
                        if '-' in custom_room_num:
                            parts = custom_room_num.split('-')
                            if len(parts) == 2 and parts[0].strip().isdigit() and parts[1].strip().isdigit():
                                start_n = int(parts[0].strip())
                                end_n = int(parts[1].strip())
                                if start_n <= end_n and (end_n - start_n) <= 100:
                                    rooms_to_create = [str(n) for n in range(start_n, end_n + 1)]
                        if not rooms_to_create:
                            rooms_to_create = [custom_room_num]
                    else:
                        existing_count = Room.objects.filter(hostel_id=hostel_id, floor=fl).exclude(capacity=0).count() + 1
                        if fl.isdigit():
                            auto_num = f"{fl}{existing_count:02d}"
                        elif fl.lower() == 'ground':
                            auto_num = f"G{existing_count:02d}"
                        else:
                            auto_num = f"{fl}-{existing_count:02d}"
                        rooms_to_create = [auto_num]

                    for room_num in rooms_to_create:
                        # PREVENT DUPLICATES: Skip if room already exists in this hostel
                        if Room.objects.filter(hostel_id=hostel_id, room_number=room_num).exclude(capacity=0).exists():
                            continue

                        # Clean up initial floor placeholder if present
                        Room.objects.filter(hostel_id=hostel_id, floor=fl, capacity=0).delete()

                        r = Room.objects.create(
                            hostel_id=hostel_id,
                            floor_obj=floor_obj,
                            sharing_type_id=sharing_type_id,
                            room_number=room_num,
                            floor=fl,
                            capacity=capacity,
                            is_active=data.get('is_active', True)
                        )
                        for i in range(1, int(r.capacity) + 1):
                            Bed.objects.create(
                                room=r,
                                bed_label=chr(64 + i) if i <= 26 else str(i),
                                status='vacant'
                            )
                        created_ids.append(r.id)

            return JsonResponse({'status': 'success', 'ids': created_ids}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@csrf_exempt
def rooms_detail(request, room_id):
    try:
        room = Room.objects.get(id=room_id)
    except Room.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Room not found'}, status=404)
        
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            old_capacity = room.capacity
            
            room.hostel_id = data.get('hostel_id', room.hostel_id)
            room.sharing_type_id = data.get('sharing_type_id', room.sharing_type_id)
            room.room_number = data.get('room_number', room.room_number)
            room.floor = data.get('floor', room.floor)
            room.capacity = data.get('capacity', room.capacity)
            room.is_active = data.get('is_active', room.is_active)
            room.save()
            
            new_capacity = room.capacity
            if new_capacity > old_capacity:
                for i in range(old_capacity + 1, new_capacity + 1):
                    Bed.objects.create(
                        room=room,
                        bed_label=chr(64 + i) if i <= 26 else str(i),
                        status='vacant'
                    )
            elif new_capacity < old_capacity:
                excess_beds = Bed.objects.filter(room=room, status='vacant').order_by('-bed_label')[:(old_capacity - new_capacity)]
                for b in excess_beds:
                    b.delete()
                    
            return JsonResponse({'status': 'success', 'message': 'Room updated'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    elif request.method == 'DELETE':
        try:
            room.delete()
            return JsonResponse({'status': 'success', 'message': 'Room deleted'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ============================================================
# INSTITUTES CRUD
# ============================================================
@csrf_exempt
def institutes_list(request):
    if request.method == 'GET':
        institutes = Institute.objects.all().order_by('code')
        data = [{
            'id': i.id,
            'code': i.code,
            'name': i.name,
            'course_type': i.course_type
        } for i in institutes]
        return JsonResponse({'status': 'success', 'data': data})
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            i = Institute.objects.create(
                code=data['code'],
                name=data['name'],
                course_type=data.get('course_type', 'UG')
            )
            return JsonResponse({'status': 'success', 'id': i.id}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@csrf_exempt
def institutes_detail(request, institute_id):
    try:
        inst = Institute.objects.get(id=institute_id)
    except Institute.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Institute not found'}, status=404)
        
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            inst.code = data.get('code', inst.code)
            inst.name = data.get('name', inst.name)
            inst.course_type = data.get('course_type', inst.course_type)
            inst.save()
            return JsonResponse({'status': 'success', 'message': 'Institute updated'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    elif request.method == 'DELETE':
        try:
            inst.delete()
            return JsonResponse({'status': 'success', 'message': 'Institute deleted'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ============================================================
# SHARING TYPES CRUD
# ============================================================
@csrf_exempt
def sharing_types_list(request):
    if request.method == 'GET':
        sharing = SharingType.objects.all().order_by('id')
        data = [{
            'id': s.id,
            'label': s.label,
            'bed_count': s.bed_count,
            'is_attached': s.is_attached
        } for s in sharing]
        return JsonResponse({'status': 'success', 'data': data})
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            s = SharingType.objects.create(
                label=data['label'],
                bed_count=data['bed_count'],
                is_attached=data.get('is_attached', True)
            )
            return JsonResponse({'status': 'success', 'id': s.id}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@csrf_exempt
def sharing_types_detail(request, sharing_type_id):
    try:
        st = SharingType.objects.get(id=sharing_type_id)
    except SharingType.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Sharing Type not found'}, status=404)
        
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            st.label = data.get('label', st.label)
            st.bed_count = data.get('bed_count', st.bed_count)
            st.is_attached = data.get('is_attached', st.is_attached)
            st.save()
            return JsonResponse({'status': 'success', 'message': 'Sharing type updated'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    elif request.method == 'DELETE':
        try:
            st.delete()
            return JsonResponse({'status': 'success', 'message': 'Sharing type deleted'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ============================================================
# USERS CRUD
# ============================================================
@csrf_exempt
def users_list(request):
    if request.method == 'GET':
        users = User.objects.all().select_related('hostel').order_by('username')
        data = [{
            'id': u.id,
            'username': u.username,
            'full_name': u.full_name,
            'role': u.role,
            'hostel_id': u.hostel_id,
            'hostel_name': u.hostel.name if u.hostel else 'All Hostels',
            'is_active': u.is_active
        } for u in users]
        return JsonResponse({'status': 'success', 'data': data})
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            password = data['password']
            salt = bcrypt.gensalt()
            password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
            
            u = User.objects.create(
                username=data['username'],
                password_hash=password_hash,
                full_name=data['full_name'],
                role=data.get('role', 'staff'),
                hostel_id=data.get('hostel_id'),
                is_active=data.get('is_active', True)
            )
            return JsonResponse({'status': 'success', 'id': u.id}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@csrf_exempt
def users_detail(request, user_id):
    try:
        user = User.objects.get(id=user_id)
    except User.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'User not found'}, status=404)
        
    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            user.username = data.get('username', user.username)
            user.full_name = data.get('full_name', user.full_name)
            user.role = data.get('role', user.role)
            user.hostel_id = data.get('hostel_id', user.hostel_id)
            user.is_active = data.get('is_active', user.is_active)
            
            password = data.get('password')
            if password:
                salt = bcrypt.gensalt()
                user.password_hash = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
                
            user.save()
            return JsonResponse({'status': 'success', 'message': 'User updated'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)
            
    elif request.method == 'DELETE':
        try:
            user.delete()
            return JsonResponse({'status': 'success', 'message': 'User deleted'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ============================================================
# RESIDENTS
# ============================================================
@csrf_exempt
def residents_list(request):
    if request.method == 'GET':
        q = request.GET.get('q')
        institute_id = request.GET.get('institute_id')
        residents = Resident.objects.all().select_related('institute')
        
        if q:
            residents = residents.filter(Q(full_name__icontains=q) | Q(reg_no__icontains=q))
        if institute_id:
            residents = residents.filter(institute_id=institute_id)
            
        residents = residents.order_by('full_name')
        
        data = [{
            'id': r.id,
            'reg_no': r.reg_no,
            'full_name': r.full_name,
            'person_type': r.person_type,
            'institute_id': r.institute_id,
            'institute_code': r.institute.code if r.institute else None,
            'year_of_study': r.year_of_study,
            'gender': r.gender,
            'phone': r.phone,
            'guardian_phone': r.guardian_phone
        } for r in residents]
        return JsonResponse({'status': 'success', 'data': data})
        
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            r = Resident.objects.create(
                reg_no=data['reg_no'],
                full_name=data['full_name'],
                person_type=data.get('person_type', 'student'),
                institute_id=data.get('institute_id') if data.get('person_type') != 'staff' else None,
                year_of_study=data.get('year_of_study') if data.get('person_type') != 'staff' else None,
                gender=data['gender'],
                phone=data.get('phone'),
                guardian_phone=data.get('guardian_phone')
            )
            return JsonResponse({'status': 'success', 'id': r.id}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@csrf_exempt
def allocations_check_in(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        resident_id = data['resident_id']
        room_id = data['room_id']
        entry_date = data.get('entry_date', timezone.now().date().isoformat())
        
        active_alloc = Allocation.objects.filter(resident_id=resident_id, status='active').first()
        if active_alloc:
            return JsonResponse({'status': 'error', 'message': 'Resident is already checked-in to Room ' + active_alloc.room.room_number}, status=400)
            
        room = Room.objects.get(id=room_id)
        if not room.is_active:
            return JsonResponse({'status': 'error', 'message': 'Selected room is currently inactive or under maintenance'}, status=400)
            
        occupied_count = 0
        with connection.cursor() as cursor:
            cursor.execute("SELECT occupied FROM vw_room_occupancy WHERE room_id = %s", [room_id])
            res = cursor.fetchone()
            if res:
                occupied_count = res[0]
                
        if occupied_count >= room.capacity:
            return JsonResponse({'status': 'error', 'message': 'Room is fully occupied'}, status=400)
            
        bed = Bed.objects.filter(room_id=room_id, status='vacant').order_by('bed_label').first()
        bed_id = bed.id if bed else None
        
        with transaction.atomic():
            alloc = Allocation.objects.create(
                resident_id=resident_id,
                room_id=room_id,
                bed_id=bed_id,
                entry_date=entry_date,
                status='active'
            )
            
            Renewal.objects.create(
                allocation=alloc,
                academic_year='2026-27',
                renewal_status='TBR'
            )
            
            if bed:
                bed.status = 'occupied'
                bed.save()
                
        return JsonResponse({'status': 'success', 'id': alloc.id}, status=201)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@csrf_exempt
def allocations_check_out(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Only POST allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        allocation_id = data['allocation_id']
        exit_date = data.get('exit_date', timezone.now().date().isoformat())
        exit_reason_desc = data.get('exit_reason')
        
        reason = ExitReason.objects.filter(description=exit_reason_desc).first()
        reason_id = reason.id if reason else None
        
        with transaction.atomic():
            alloc = Allocation.objects.select_for_update().get(id=allocation_id, status='active')
            alloc.status = 'exited'
            alloc.exit_date = exit_date
            alloc.exit_reason_id = reason_id
            alloc.save()
            
            if alloc.bed:
                bed = alloc.bed
                bed.status = 'vacant'
                bed.save()
                
        return JsonResponse({'status': 'success', 'message': 'Check-out completed'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def renewals_list(request):
    renewals = Renewal.objects.all().select_related('allocation', 'allocation__resident', 'allocation__room', 'allocation__room__hostel').order_by('-updated_at')
    data = [{
        'id': r.id,
        'allocation_id': r.allocation_id,
        'resident_name': r.allocation.resident.full_name,
        'reg_no': r.allocation.resident.reg_no,
        'hostel_name': r.allocation.room.hostel.name,
        'room_number': r.allocation.room.room_number,
        'academic_year': r.academic_year,
        'renewal_status': r.renewal_status,
        'updated_at': r.updated_at.isoformat()
    } for r in renewals]
    return JsonResponse({'status': 'success', 'data': data})

@csrf_exempt
def renewals_update(request, renewal_id):
    if request.method != 'PUT':
        return JsonResponse({'status': 'error', 'message': 'Only PUT allowed'}, status=405)
        
    try:
        data = json.loads(request.body)
        renewal = Renewal.objects.get(id=renewal_id)
        renewal.renewal_status = data['renewal_status']
        renewal.save()
        return JsonResponse({'status': 'success', 'message': 'Renewal status updated'})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def requirements_list(request):
    try:
        gaps = []
        with connection.cursor() as cursor:
            cursor.execute("SELECT requirement_id, institute, gender, sharing_type, academic_year, required_beds, available_now, difference FROM vw_requirement_gap")
            for r in cursor.fetchall():
                gaps.append({
                    'id': r[0],
                    'institute': r[1],
                    'gender': r[2],
                    'sharing_type': r[3],
                    'academic_year': r[4],
                    'required_beds': r[5],
                    'available_now': r[6],
                    'difference': r[7]
                })
        return JsonResponse({'status': 'success', 'data': gaps})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

@csrf_exempt
def construction_list(request):
    if request.method == 'GET':
        phases = ConstructionPhase.objects.all().select_related('hostel').order_by('completion_date')
        data = [{
            'id': p.id,
            'hostel_name': p.hostel.name,
            'phase_name': p.phase_name,
            'beds_added': p.beds_added,
            'completion_date': p.completion_date.isoformat() if p.completion_date else None,
            'status': p.status
        } for p in phases]
        return JsonResponse({'status': 'success', 'data': data})
        
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            p = ConstructionPhase.objects.create(
                hostel_id=data['hostel_id'],
                phase_name=data['phase_name'],
                beds_added=data['beds_added'],
                completion_date=data.get('completion_date'),
                status=data.get('status', 'planned')
            )
            return JsonResponse({'status': 'success', 'id': p.id}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

def summary_occupancy(request):
    try:
        hostel_id = request.GET.get('hostel_id')
        sharing_type_id = request.GET.get('sharing_type_id')
        institute_id = request.GET.get('institute_id')
        
        query = Allocation.objects.filter(status='active', resident__person_type='student')
        
        if hostel_id and hostel_id != 'all':
            query = query.filter(room__hostel_id=hostel_id)
        if sharing_type_id and sharing_type_id != 'all':
            query = query.filter(room__sharing_type_id=sharing_type_id)
        if institute_id and institute_id != 'all':
            query = query.filter(resident__institute_id=institute_id)
            
        aggregates = query.values(
            'room__hostel__id', 'room__hostel__name', 
            'room__sharing_type__id', 'room__sharing_type__label'
        ).annotate(student_count=Count('id')).order_by('room__hostel__name', 'room__sharing_type__label')
        
        results = []
        for agg in aggregates:
            results.append({
                'hostel_id': agg['room__hostel__id'],
                'hostel_name': agg['room__hostel__name'],
                'sharing_type_id': agg['room__sharing_type__id'],
                'sharing_type_label': agg['room__sharing_type__label'],
                'student_count': agg['student_count']
            })
            
        return JsonResponse({'status': 'success', 'data': results})
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def allocations_list(request):
    if request.method == 'GET':
        try:
            allocs = Allocation.objects.all().select_related('resident', 'room', 'room__hostel', 'bed', 'exit_reason').order_by('-entry_date')
            data = [{
                'id': a.id,
                'resident_id': a.resident_id,
                'resident_name': a.resident.full_name,
                'resident_reg_no': a.resident.reg_no,
                'resident_gender': a.resident.gender,
                'hostel_id': a.room.hostel_id,
                'hostel_name': a.room.hostel.name,
                'room_id': a.room_id,
                'room_number': a.room.room_number,
                'bed_id': a.bed_id,
                'bed_label': a.bed.bed_label if a.bed else '',
                'entry_date': a.entry_date.isoformat() if a.entry_date else '',
                'exit_date': a.exit_date.isoformat() if a.exit_date else None,
                'exit_reason': a.exit_reason.description if a.exit_reason else '',
                'status': a.status
            } for a in allocs]
            return JsonResponse({'status': 'success', 'data': data})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def exit_reasons_list(request):
    if request.method == 'GET':
        try:
            reasons = ExitReason.objects.all().order_by('description')
            data = [{'id': r.id, 'description': r.description} for r in reasons]
            return JsonResponse({'status': 'success', 'data': data})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def report_monthly(request):
    if request.method == 'GET':
        try:
            import calendar
            from datetime import date
            
            # Generate the last 6 months list (Year, Month)
            today = date.today()
            months = []
            for i in range(5, -1, -1):
                m = today.month - i
                y = today.year
                while m <= 0:
                    m += 12
                    y -= 1
                months.append((y, m))
                
            data = []
            for y, m in months:
                first_day = date(y, m, 1)
                last_day_val = calendar.monthrange(y, m)[1]
                last_day = date(y, m, last_day_val)
                
                # Active allocations during the given month:
                # entry_date <= last_day AND (exit_date is NULL OR exit_date >= first_day)
                allocs = Allocation.objects.filter(
                    entry_date__lte=last_day
                ).exclude(
                    status='cancelled'
                ).select_related('resident')
                
                active_allocs = [a for a in allocs if a.exit_date is None or a.exit_date >= first_day]
                
                students = sum(1 for a in active_allocs if a.resident.person_type == 'student')
                staff = sum(1 for a in active_allocs if a.resident.person_type == 'staff')
                
                month_label = first_day.strftime('%B %Y')
                data.append({
                    'month_label': month_label,
                    'student_count': students,
                    'staff_count': staff,
                    'total_count': students + staff
                })
                
            return JsonResponse({'status': 'success', 'data': data})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def report_daily(request):
    if request.method == 'GET':
        try:
            from datetime import date, timedelta
            today = date.today()
            daily_data = []
            for i in range(6, -1, -1):
                d = today - timedelta(days=i)
                check_ins = Allocation.objects.filter(entry_date=d).count()
                check_outs = Allocation.objects.filter(exit_date=d).count()
                active = Allocation.objects.filter(entry_date__lte=d, status='active').count()
                daily_data.append({
                    'date_label': d.strftime('%d %b %Y'),
                    'check_ins': check_ins,
                    'check_outs': check_outs,
                    'active_residents': active
                })
            return JsonResponse({'status': 'success', 'data': daily_data})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

def report_opening_closing(request):
    if request.method == 'GET':
        try:
            hostels = Hostel.objects.all().order_by('name')
            data = []
            for h in hostels:
                total_rooms = Room.objects.filter(hostel=h).exclude(capacity=0)
                total_beds = sum(r.capacity for r in total_rooms)
                occupied = Allocation.objects.filter(room__hostel=h, status='active').count()
                vacant = max(0, total_beds - occupied)
                data.append({
                    'hostel_id': h.id,
                    'hostel_name': h.name,
                    'gender': h.gender,
                    'total_rooms': total_rooms.count(),
                    'opening_total_beds': total_beds,
                    'occupied_beds': occupied,
                    'closing_vacant_beds': vacant,
                    'occupancy_rate': round((occupied / total_beds * 100)) if total_beds > 0 else 0
                })
            return JsonResponse({'status': 'success', 'data': data})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

# ============================================================
# FLOORS CRUD
# ============================================================
@csrf_exempt
def floors_list(request):
    if request.method == 'GET':
        hostel_id = request.GET.get('hostel_id')
        floors = Floor.objects.all().select_related('hostel')
        if hostel_id:
            floors = floors.filter(hostel_id=hostel_id)
        floors_list = list(floors.select_related('hostel'))
        floors_list.sort(key=lambda f: (f.hostel.name if f.hostel else '', int(f.floor_number) if f.floor_number.isdigit() else 999))
        data = [{
            'id': f.id,
            'hostel_id': f.hostel_id,
            'hostel_name': f.hostel.name if f.hostel else '',
            'floor_number': f.floor_number,
            'floor_name': f.floor_name
        } for f in floors_list]
        return JsonResponse({'status': 'success', 'data': data})
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            f = Floor.objects.create(
                hostel_id=data['hostel_id'],
                floor_number=data['floor_number'],
                floor_name=data.get('floor_name')
            )
            return JsonResponse({'status': 'success', 'id': f.id}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

@csrf_exempt
def floors_detail(request, floor_id):
    try:
        floor = Floor.objects.get(id=floor_id)
    except Floor.DoesNotExist:
        return JsonResponse({'status': 'error', 'message': 'Floor not found'}, status=404)

    if request.method == 'PUT':
        try:
            data = json.loads(request.body)
            floor.floor_number = data.get('floor_number', floor.floor_number)
            floor.floor_name = data.get('floor_name', f"Floor {data.get('floor_number', floor.floor_number)}")
            floor.save()
            return JsonResponse({'status': 'success', 'message': 'Floor updated'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

    elif request.method == 'DELETE':
        try:
            Room.objects.filter(hostel_id=floor.hostel_id, floor=floor.floor_number).delete()
            floor.delete()
            return JsonResponse({'status': 'success', 'message': 'Floor deleted'})
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ============================================================
# ROOM BEDS SHARE CRUD
# ============================================================
@csrf_exempt
def room_beds_share_list(request):
    if request.method == 'GET':
        shares = RoomBedsShare.objects.all().select_related('floor', 'hostel', 'room')
        data = [{
            'id': s.id,
            'floor_id': s.floor_id,
            'floor_number': s.floor.floor_number if s.floor else '',
            'hostel_id': s.hostel_id,
            'hostel_name': s.hostel.name if s.hostel else '',
            'room_id': s.room_id,
            'room_number': s.room.room_number if s.room else '',
            'beds_share': s.beds_share
        } for s in shares]
        return JsonResponse({'status': 'success', 'data': data})
    elif request.method == 'POST':
        try:
            data = json.loads(request.body)
            s = RoomBedsShare.objects.create(
                floor_id=data['floor_id'],
                hostel_id=data['hostel_id'],
                room_id=data['room_id'],
                beds_share=data['beds_share']
            )
            return JsonResponse({'status': 'success', 'id': s.id}, status=201)
        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=400)

# ============================================================
# DATABASE INITIALIZER / SCHEMA MIGRATION FUNCTION FOR PGADMIN
# ============================================================
@csrf_exempt
def init_db_schema(request):
    """
    Executes PostgreSQL DDL DDL script to create/recreate normalized tables
    (institutes, hostels, floors, rooms, room_beds_share, residents/students)
    and seeds sample data matching user's ERD diagram for pgAdmin view.
    """
    import os
    try:
        schema_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../db/hostel-database-schema.sql'))
        if not os.path.exists(schema_path):
            schema_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../hostel-database-schema.sql'))

        with open(schema_path, 'r', encoding='utf-8') as f:
            sql_script = f.read()

        with connection.cursor() as cursor:
            cursor.execute(sql_script)

        # Seed Admin user
        if not User.objects.filter(username='admin').exists():
            salt = bcrypt.gensalt()
            admin_pwd_hash = bcrypt.hashpw(b'admin123', salt).decode('utf-8')
            User.objects.create(
                username='admin',
                password_hash=admin_pwd_hash,
                full_name='System Admin',
                role='admin',
                hostel=None,
                is_active=True
            )

        # Seed Institutes matching ERD
        institutes_data = [
            ("RGU-ARTS", "RGU ARTS"),
            ("RGU-RSMART", "RGU R-SMART"),
            ("RGU-PRO", "RGU R-SMART PRO"),
            ("RGU-INT-ARTS", "RGU R-SMART INTELLECT (ARTS)"),
            ("RGU-INT-RTC", "RGU R-SMART INTELLECT (RTC)"),
            ("RGU-ENGG", "RGU ENGINEERING"),
            ("RGU-INT-ENGG", "RGU R-SMART INTELLECT (ENGG)"),
            ("RTC", "RTC"),
            ("RTC-INTELLECT", "RTC R-SMART INTELLECT"),
            ("RCP", "RCP"),
            ("RPH", "RPH"),
        ]
        inst_objs = []
        for code, name in institutes_data:
            inst, _ = Institute.objects.get_or_create(code=code, defaults={'name': name, 'course_type': 'UG'})
            inst_objs.append(inst)

        # Seed Hostels matching ERD
        hostels_data = [
            ("Chillies", "Boys"),
            ("White", "Girls"),
            ("KPM", "Boys"),
            ("Kings 1", "Boys"),
            ("Kings 2", "Boys"),
            ("Kings 3", "Boys"),
            ("Westend", "Boys"),
            ("Kings 4", "Boys"),
            ("Grand Hall", "Boys"),
            ("Eachanari", "Boys"),
        ]
        hostel_objs = []
        for name, gender in hostels_data:
            h, _ = Hostel.objects.get_or_create(name=name, gender=gender)
            hostel_objs.append(h)

        # Seed Floors for Hostel 1 (Chillies)
        chillies_hostel = hostel_objs[0] if hostel_objs else Hostel.objects.first()
        floor_objs = []
        for fl_num in ['1', '2', '3', '4']:
            fl, _ = Floor.objects.get_or_create(hostel=chillies_hostel, floor_number=fl_num, defaults={'floor_name': f"Floor {fl_num}"})
            floor_objs.append(fl)

        # Seed Rooms for Floor 1
        floor1 = floor_objs[0] if floor_objs else Floor.objects.first()
        room_objs = []
        for r_num in ['101', '102', '103', '104']:
            r, _ = Room.objects.get_or_create(
                hostel=chillies_hostel,
                room_number=r_num,
                defaults={'floor_obj': floor1, 'floor': '1', 'capacity': 4, 'is_active': True}
            )
            room_objs.append(r)

        # Seed RoomBedsShare entries matching ERD
        room1 = room_objs[0] if room_objs else Room.objects.first()
        room2 = room_objs[1] if len(room_objs) > 1 else room1
        room3 = room_objs[2] if len(room_objs) > 2 else room1

        sh1, _ = RoomBedsShare.objects.get_or_create(floor=floor1, hostel=chillies_hostel, room=room1, beds_share='2normal')
        sh2, _ = RoomBedsShare.objects.get_or_create(floor=floor1, hostel=chillies_hostel, room=room2, beds_share='3 sharing')
        sh3, _ = RoomBedsShare.objects.get_or_create(floor=floor1, hostel=chillies_hostel, room=room3, beds_share='4 sharing')

        # Seed Resident / Student matching ERD (snajay)
        inst1 = inst_objs[0] if inst_objs else Institute.objects.first()
        Resident.objects.get_or_create(
            reg_no='RTC2026ST001',
            defaults={
                'full_name': 'snajay',
                'person_type': 'student',
                'institute': inst1,
                'hostel': chillies_hostel,
                'floor': floor1,
                'room': room1,
                'sh': sh1,
                'gender': 'Male',
                'year_of_study': 1
            }
        )

        return JsonResponse({
            'status': 'success',
            'message': 'PostgreSQL DDL schema initialized successfully! All normalized tables are now visible in pgAdmin.',
            'tables': ['institutes', 'hostels', 'floors', 'rooms', 'room_beds_share', 'residents', 'beds', 'allocations']
        })
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

