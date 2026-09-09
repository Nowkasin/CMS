from django.urls import path

from . import views

urlpatterns = [
    path('', views.step1_upload, name='step1'),
    path('review/', views.step2_review, name='step2'),
    path('review/edit/<int:idx>/', views.edit_staged_row, name='edit_row'),
    path('confirm/', views.step3_confirm, name='step3'),
    path('done/', views.step4_done, name='step4'),
    path('restart/', views.restart, name='restart'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/edit/<str:subarea_id>/', views.edit_meter, name='edit_meter'),
    path('dashboard/export/', views.export_meters_excel, name='export_meters'),
    
]