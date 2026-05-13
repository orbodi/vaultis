from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("equipment/<int:pk>/", views.equipment_detail, name="equipment_detail"),
    path("equipment/<int:pk>/backup/", views.equipment_backup, name="equipment_backup"),
]
