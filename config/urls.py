from django.urls import path, include

urlpatterns = [
    path('', include('meters.urls')),
]

handler404 = 'meters.views.errors.page_not_found'
