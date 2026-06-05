from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import BackupScheduleForm
from .models import BackupJob, BackupSchedule, Equipment, EquipmentHost
from .nethsm_credentials import default_nethsm_credentials_configured
from .scheduler import compute_next_run, schedule_summary
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
    )[:5]
    slug = equipment.equipment_type.slug
    is_nitrokey = slug == "nitrokey"
    is_arbor_aed = slug == "ddos"
    has_default_credentials = default_nethsm_credentials_configured() if is_nitrokey else False
    schedule = BackupSchedule.objects.filter(equipment=equipment).first()
    schedule_form = BackupScheduleForm(equipment=equipment, instance=schedule)
    schedule_summary_text = schedule_summary(schedule) if schedule else ""
    return render(
        request,
        "equipment/detail.html",
        {
            "equipment": equipment,
            "jobs": jobs,
            "requires_host_selection": not is_arbor_aed,
            "requires_api_credentials": is_nitrokey,
            "is_arbor_aed": is_arbor_aed,
            "arbor_active_dcs_display": getattr(settings, "ARBOR_AED_ACTIVE_DCS", "") if is_arbor_aed else "",
            "has_default_nethsm_credentials": has_default_credentials,
            "default_nethsm_username": getattr(settings, "NITROKEY_NETHSM_USER", "") if has_default_credentials else "",
            "schedule": schedule,
            "schedule_form": schedule_form,
            "schedule_summary": schedule_summary_text,
            "django_timezone": settings.TIME_ZONE,
        },
    )


@login_required
@require_POST
def equipment_backup(request, pk: int):
    equipment = get_object_or_404(Equipment, pk=pk)
    equipment_host = None
    if equipment.equipment_type.slug != "ddos":
        host_qs = EquipmentHost.objects.filter(equipment=equipment).order_by(
            "sort_order",
            "pk",
        )
        if not host_qs.exists():
            messages.error(request, "Aucun host configuré.")
            return redirect("equipment_detail", pk=equipment.pk)
        raw_host_id = request.POST.get("equipment_host_id", "").strip()
        if not raw_host_id.isdigit():
            messages.error(request, "Host requis.")
            return redirect("equipment_detail", pk=equipment.pk)
        equipment_host = get_object_or_404(host_qs, pk=int(raw_host_id))

    credentials = None
    if equipment.equipment_type.slug == "nitrokey":
        credentials_mode = request.POST.get("credentials_mode", "default").strip().lower()
        if credentials_mode == "custom":
            username = request.POST.get("api_username", "").strip()
            password = request.POST.get("api_password", "")
            if not username or not password:
                messages.error(request, "Identifiants API personnalisés requis.")
                return redirect("equipment_detail", pk=equipment.pk)
            credentials = {"username": username, "password": password}
        elif not default_nethsm_credentials_configured():
            messages.error(
                request,
                "Identifiants par défaut non configurés sur le serveur (.env).",
            )
            return redirect("equipment_detail", pk=equipment.pk)

    job = BackupJob.objects.create(
        equipment=equipment,
        equipment_host=equipment_host,
        triggered_by=request.user,
        trigger=BackupJob.Trigger.MANUAL,
    )
    run_backup_job(job, credentials=credentials)
    job.refresh_from_db()
    if job.status == BackupJob.Status.SUCCESS:
        messages.success(request, job.message or "Sauvegarde réussie.")
    else:
        messages.error(request, job.message or "Échec de la sauvegarde.")
    return redirect("equipment_detail", pk=equipment.pk)


@login_required
@require_POST
def equipment_schedule(request, pk: int):
    equipment = get_object_or_404(
        Equipment.objects.select_related("equipment_type").prefetch_related(_HOSTS_PREFETCH),
        pk=pk,
    )
    schedule = BackupSchedule.objects.filter(equipment=equipment).first()
    form = BackupScheduleForm(equipment=equipment, data=request.POST, instance=schedule)

    if not form.is_valid():
        for err in form.non_field_errors():
            messages.error(request, err)
        for field, errors in form.errors.items():
            if field == "__all__":
                continue
            for err in errors:
                messages.error(request, f"Planification — {err}")
        return redirect("equipment_detail", pk=equipment.pk)

    saved = form.save(commit=False)
    saved.equipment = equipment
    if saved.is_enabled:
        saved.next_run_at = compute_next_run(saved)
    else:
        saved.next_run_at = None
    saved.save()

    if saved.is_enabled:
        messages.success(
            request,
            f"Planification enregistrée : {schedule_summary(saved)}. "
            f"Prochaine exécution : {saved.next_run_at:%d/%m/%Y %H:%M} ({settings.TIME_ZONE}).",
        )
    else:
        messages.success(request, "Planification automatique désactivée.")
    return redirect("equipment_detail", pk=equipment.pk)
