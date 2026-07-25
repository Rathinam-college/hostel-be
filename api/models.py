from django.db import models

class Institute(models.Model):
    id = models.AutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=120)
    course_type = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'institutes'

class SharingType(models.Model):
    id = models.AutoField(primary_key=True)
    label = models.CharField(max_length=60, unique=True)
    bed_count = models.IntegerField()
    is_attached = models.BooleanField(default=True)

    class Meta:
        db_table = 'sharing_types'

class Hostel(models.Model):
    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=80)
    gender = models.CharField(max_length=20)
    warden_name = models.CharField(max_length=100, null=True)
    warden_phone = models.CharField(max_length=20, null=True)

    class Meta:
        db_table = 'hostels'

class Floor(models.Model):
    id = models.AutoField(primary_key=True)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, db_column='hostel_id')
    floor_number = models.CharField(max_length=20)
    floor_name = models.CharField(max_length=60, null=True, blank=True)

    class Meta:
        db_table = 'floors'

class Room(models.Model):
    id = models.AutoField(primary_key=True)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, db_column='hostel_id')
    floor_obj = models.ForeignKey(Floor, on_delete=models.CASCADE, db_column='floor_id', null=True, blank=True)
    sharing_type = models.ForeignKey(SharingType, on_delete=models.SET_NULL, db_column='sharing_type_id', null=True, blank=True)
    room_number = models.CharField(max_length=20)
    floor = models.CharField(max_length=20, null=True)
    capacity = models.IntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'rooms'

class RoomBedsShare(models.Model):
    id = models.AutoField(primary_key=True)
    floor = models.ForeignKey(Floor, on_delete=models.CASCADE, db_column='floor_id')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, db_column='hostel_id')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, db_column='room_id')
    beds_share = models.CharField(max_length=60)

    class Meta:
        db_table = 'room_beds_share'

class Bed(models.Model):
    id = models.AutoField(primary_key=True)
    room = models.ForeignKey(Room, on_delete=models.CASCADE, db_column='room_id')
    bed_label = models.CharField(max_length=10)
    status = models.CharField(max_length=20, default='vacant')

    class Meta:
        db_table = 'beds'

class Resident(models.Model):
    id = models.AutoField(primary_key=True)
    reg_no = models.CharField(max_length=40, unique=True)
    full_name = models.CharField(max_length=120)
    person_type = models.CharField(max_length=20, default='student')
    institute = models.ForeignKey(Institute, on_delete=models.SET_NULL, null=True, db_column='institute_id')
    hostel = models.ForeignKey(Hostel, on_delete=models.SET_NULL, null=True, db_column='hostel_id')
    floor = models.ForeignKey(Floor, on_delete=models.SET_NULL, null=True, db_column='floor_id')
    room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, db_column='room_id')
    sh = models.ForeignKey(RoomBedsShare, on_delete=models.SET_NULL, null=True, db_column='sh_id')
    year_of_study = models.IntegerField(null=True)
    gender = models.CharField(max_length=20)
    phone = models.CharField(max_length=20, null=True)
    guardian_phone = models.CharField(max_length=20, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'residents'

class ExitReason(models.Model):
    id = models.AutoField(primary_key=True)
    description = models.CharField(max_length=80, unique=True)

    class Meta:
        db_table = 'exit_reasons'

class Allocation(models.Model):
    id = models.AutoField(primary_key=True)
    resident = models.ForeignKey(Resident, on_delete=models.PROTECT, db_column='resident_id')
    room = models.ForeignKey(Room, on_delete=models.PROTECT, db_column='room_id')
    bed = models.ForeignKey(Bed, on_delete=models.SET_NULL, null=True, db_column='bed_id')
    entry_date = models.DateField()
    exit_date = models.DateField(null=True)
    exit_reason = models.ForeignKey(ExitReason, on_delete=models.SET_NULL, null=True, db_column='exit_reason_id')
    status = models.CharField(max_length=20, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'allocations'

class Renewal(models.Model):
    id = models.AutoField(primary_key=True)
    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, db_column='allocation_id')
    academic_year = models.CharField(max_length=9)
    renewal_status = models.CharField(max_length=20, default='TBR')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'renewals'

class Requirement(models.Model):
    id = models.AutoField(primary_key=True)
    institute = models.ForeignKey(Institute, on_delete=models.CASCADE, db_column='institute_id')
    sharing_type = models.ForeignKey(SharingType, on_delete=models.CASCADE, db_column='sharing_type_id')
    gender = models.CharField(max_length=20)
    academic_year = models.CharField(max_length=9)
    required_beds = models.IntegerField(default=0)
    expected_date = models.DateField(null=True)
    notes = models.CharField(max_length=255, null=True)

    class Meta:
        db_table = 'requirements'

class ConstructionPhase(models.Model):
    id = models.AutoField(primary_key=True)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, db_column='hostel_id')
    phase_name = models.CharField(max_length=100)
    beds_added = models.IntegerField()
    completion_date = models.DateField(null=True)
    status = models.CharField(max_length=20, default='planned')

    class Meta:
        db_table = 'construction_phases'

class User(models.Model):
    id = models.AutoField(primary_key=True)
    username = models.CharField(max_length=60, unique=True)
    password_hash = models.CharField(max_length=255)
    full_name = models.CharField(max_length=120)
    role = models.CharField(max_length=20, default='staff')
    hostel = models.ForeignKey(Hostel, on_delete=models.SET_NULL, null=True, db_column='hostel_id')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'users'
