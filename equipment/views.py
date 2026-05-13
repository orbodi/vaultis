import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import BackupJob, Equipment, EquipmentHost
from .services import run_backup_job

_HOSTS_PREFETCH = Prefetch(
    "hosts",
    queryset=EquipmentHost.objects.order_by("sort_order", "pk"),
)


@login_required
def home(request):
    equipments = (
        Equipment.objects.select_related("equipment_type")
        .prefetch_related(_HOSTS_PREFETCH)
        .all()
    )
    return render(request, "equipment/home.html", {"equipments": equipments})


@login_required
def equipment_detail(request, pk: int):
    equipment = get_object_or_404(
        Equipment.objects.select_related("equipment_type").prefetch_related(
            _HOSTS_PREFETCH
        ),
        pk=pk,
    )
    jobs = equipment.backup_jobs.select_related(
        "triggered_by",
        "equipment_host",
    )[:20]
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
    host_qs = EquipmentHost.objects.filter(equipment=equipment).order_by(
        "sort_order",
        "pk",
    )
    if not host_qs.exists():
        messages.error(
            request,
            "Aucun host de management n’est configuré pour cet équipement.",
        )
        return redirect("equipment_detail", pk=equipment.pk)
    raw_host_id = request.POST.get("equipment_host_id", "").strip()
    if not raw_host_id.isdigit():
        messages.error(request, "Veuillez sélectionner un host de management.")
        return redirect("equipment_detail", pk=equipment.pk)
    equipment_host = get_object_or_404(host_qs, pk=int(raw_host_id))
    job = BackupJob.objects.create(
        equipment=equipment,
        equipment_host=equipment_host,
        triggered_by=request.user,
    )
    run_backup_job(job)
    messages.success(request, "Sauvegarde terminée (mode démo).")
    return redirect("equipment_detail", pk=equipment.pk)
