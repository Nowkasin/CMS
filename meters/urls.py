from django.urls import path

from . import views

urlpatterns = [
    path('', views.step1_upload, name='step1'),
    path('review/', views.step2_review, name='step2'),
    path('confirm/', views.step3_confirm, name='step3'),
    path('done/', views.step4_done, name='step4'),
    path('restart/', views.restart, name='restart'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('create_contract/', views.create_contract, name='create_contract'),
]