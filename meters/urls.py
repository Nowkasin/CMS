from django.urls import path

from . import views

urlpatterns = [
    path('', views.step1_upload, name='step1'),
    path('review/', views.step2_review, name='step2'),
    path('confirm/', views.step3_confirm, name='step3'),
    path('done/', views.step4_done, name='step4'),
    path('restart/', views.restart, name='restart'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/edit/<str:subarea_id>/', views.edit_meter, name='edit_meter'),
    path('dashboard/export/', views.export_meters_excel, name='export_meters'),

    # --- ยกเลิกสัญญา (ของใหม่) ---
    path('termination/', views.termination_search, name='termination_search'),
    path('termination/<int:contract_id>/', views.termination_detail, name='termination_detail'),
    path(
        'termination/<int:contract_id>/toggle/<str:period>/',
        views.termination_toggle_installment,
        name='termination_toggle',
    ),
    path(
        'termination/<int:contract_id>/toggle-all/',
        views.termination_select_all_installments,
        name='termination_toggle_all',
    ),
    path(
        'termination/<int:contract_id>/delete/',
        views.termination_delete,
        name='termination_delete',
    ),
    path(
        'termination/<int:contract_id>/close-meters/',
        views.termination_close_meters,
        name='termination_close_meters',
    ),
    # ต้องอยู่ก่อน <int:contract_id> ไม่จำเป็น เพราะ 'log' ไม่ match int converter
    # แต่วางไว้ให้อ่านง่ายว่าเป็น URL ระดับเดียวกัน
    path('termination/log/', views.termination_log, name='termination_log'),
        # --- ดาวน์โหลด Excel รายชื่อสัญญา + เลขอ่านมิเตอร์ ---
    path('download/', views.download_form, name='download_form'),
    path('download/excel/', views.download_excel, name='download_excel'),
    path('meters/', views.meter_list, name='meter_list'),
    path('meters/new/', views.meter_form, name='meter_new'),
    path('meters/<int:meter_id>/edit/', views.meter_form, name='meter_edit'),

    # --- Master ระบบไฟฟ้า (1 เฟส / 3 เฟส) ---
    path('phases/', views.phase_list, name='phase_list'),
    path('phases/new/', views.phase_form, name='phase_new'),
    path('phases/<int:phase_id>/edit/', views.phase_form, name='phase_edit'),
]