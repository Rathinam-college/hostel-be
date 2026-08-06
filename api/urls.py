from django.urls import path
from . import views

urlpatterns = [
    path('auth/login', views.auth_login, name='auth_login'),
    path('dashboard/stats', views.dashboard_stats, name='dashboard_stats'),
    
    # Hostels CRUD
    path('hostels', views.hostels_list, name='hostels_list'),
    path('hostels/<int:hostel_id>', views.hostels_detail, name='hostels_detail'),
    
    # Rooms CRUD
    path('rooms', views.rooms_list, name='rooms_list'),
    path('rooms/<int:room_id>', views.rooms_detail, name='rooms_detail'),
    
    # Institutes CRUD
    path('institutes', views.institutes_list, name='institutes_list'),
    path('institutes/<int:institute_id>', views.institutes_detail, name='institutes_detail'),
    
    # Sharing Types CRUD
    path('sharing-types', views.sharing_types_list, name='sharing_types_list'),
    path('sharing-types/<int:sharing_type_id>', views.sharing_types_detail, name='sharing_types_detail'),
    
    # Users CRUD
    path('users', views.users_list, name='users_list'),
    path('users/<int:user_id>', views.users_detail, name='users_detail'),
    
    # Resident & Allocation operations
    path('residents/promote-year', views.residents_promote_year, name='residents_promote_year'),
    path('residents', views.residents_list, name='residents_list'),
    path('residents/<int:resident_id>', views.residents_detail, name='residents_detail'),
    path('allocations/check-in', views.allocations_check_in, name='allocations_check_in'),
    path('allocations/check-out', views.allocations_check_out, name='allocations_check_out'),
    path('allocations', views.allocations_list, name='allocations_list'),
    path('exit-reasons', views.exit_reasons_list, name='exit_reasons_list'),
    
    # Renewals, requirements & construction
    path('renewals', views.renewals_list, name='renewals_list'),
    path('renewals/<int:renewal_id>', views.renewals_update, name='renewals_update'),
    path('requirements', views.requirements_list, name='requirements_list'),
    path('construction', views.construction_list, name='construction_list'),
    # Floors & Room Beds Share CRUD
    path('floors', views.floors_list, name='floors_list'),
    path('floors/<int:floor_id>', views.floors_detail, name='floors_detail'),
    path('room-beds-share', views.room_beds_share_list, name='room_beds_share_list'),
    
    # Reports Endpoints
    path('reports/monthly', views.report_monthly, name='report_monthly'),
    path('reports/daily', views.report_daily, name='report_daily'),
    path('reports/opening-closing', views.report_opening_closing, name='report_opening_closing'),

    # DB Schema & pgAdmin Initializer
    path('db/init-schema', views.init_db_schema, name='init_db_schema'),
]
