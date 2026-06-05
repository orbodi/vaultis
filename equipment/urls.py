from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("equipment/<int:pk>/", views.equipment_detail, name="equipment_detail"),
    path("equipment/<int:pk>/backup/", views.equipment_backup, name="equipment_backup"),
    path("equipment/<int:pk>/schedule/", views.equipment_schedule, name="equipment_schedule"),
    path("equipment/<int:pk>/jobs.json", views.equipment_jobs_json, name="equipment_jobs_json"),
]
