import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import BackupJob, Equipment
from .services import run_backup_job


@login_required
def home(request):
    equipments = Equipment.objects.select_related("equipment_type").all()
    return render(request, "equipment/home.html", {"equipments": equipments})


@login_required
def equipment_detail(request, pk: int):
    equipment = get_object_or_404(
        Equipment.objects.select_related("equipment_type"),
        pk=pk,
    )
    jobs = equipment.backup_jobs.select_related("triggered_by")[:20]
    extra_json = ""
    if equipment.extra:
        extra_json = json.dumps(equipment.extra, indent=2, ensure_ascii=False)
    return render(
        request,
        "equipment/detail.html",
        {
            "equipment": equipment,
            "jobs": jobs,
            "extra_json": extra_json,
        },
    )


@login_required
@require_POST
def equipment_backup(request, pk: int):
    equipment = get_object_or_404(Equipment, pk=pk)
    job = BackupJob.objects.create(
        equipment=equipment,
        triggered_by=request.user,
    )
    run_backup_job(job)
    messages.success(request, "Sauvegarde terminée (mode démo).")
    return redirect("equipment_detail", pk=equipment.pk)
