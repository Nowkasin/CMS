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