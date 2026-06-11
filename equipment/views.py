import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from .forms import BackupScheduleForm
from .job_history import jobs_history_payload
from .models import BackupJob, BackupSchedule, Equipment, EquipmentHost
from .f5_credentials import default_f5_credentials_configured, env_f5_user_password
from .f5_variant import (
    is_f5_family_slug,
    is_f5_ha_equipment,
    is_f5_ha_slug,
    is_f5_standalone_equipment,
    is_f5_standalone_slug,
)
from .nethsm_credentials import default_nethsm_credentials_configured
from .scheduler import compute_next_run, schedule_summary
from .services import run_backup_job_async

logger = logging.getLogger(__name__)

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
    jobs = list(
        equipment.backup_jobs.select_related(
            "triggered_by",
            "equipment_host",
        )[:5]
    )
    has_running_job = any(
        j.status in (BackupJob.Status.RUNNING, BackupJob.Status.PENDING)
        for j in jobs
    )
    slug = equipment.equipment_type.slug
    adapter_key = equipment.equipment_type.adapter_key or ""
    is_nitrokey = slug == "nitrokey"
    is_f5_standalone = is_f5_standalone_equipment(slug, adapter_key)
    is_f5_ha = is_f5_ha_equipment(slug, adapter_key)
    is_f5_family = is_f5_family_slug(slug) or is_f5_standalone
    is_arbor_aed = slug == "ddos"
    requires_api_credentials = is_nitrokey or is_f5_family
    if is_nitrokey:
        has_default_credentials = default_nethsm_credentials_configured()
        default_api_username = getattr(settings, "NITROKEY_NETHSM_USER", "") if has_default_credentials else ""
    elif is_f5_family:
        has_default_credentials = default_f5_credentials_configured()
        default_api_username = env_f5_user_password()[0] if has_default_credentials else ""
    else:
        has_default_credentials = False
        default_api_username = ""
    schedule = BackupSchedule.objects.filter(equipment=equipment).first()
    schedule_form = BackupScheduleForm(equipment=equipment, instance=schedule)
    schedule_summary_text = schedule_summary(schedule) if schedule else ""
    return render(
        request,
        "equipment/detail.html",
        {
            "equipment": equipment,
            "jobs": jobs,
            "requires_host_selection": slug not in ("ddos", "f5"),
            "requires_api_credentials": requires_api_credentials,
            "is_arbor_aed": is_arbor_aed,
            "is_f5_ha": is_f5_ha,
            "is_f5_standalone": is_f5_standalone,
            "is_f5_family": is_f5_family,
            "arbor_active_dcs_display": getattr(settings, "ARBOR_AED_ACTIVE_DCS", "") if is_arbor_aed else "",
            "has_default_api_credentials": has_default_credentials,
            "default_api_username": default_api_username,
            "schedule": schedule,
            "schedule_form": schedule_form,
            "schedule_summary": schedule_summary_text,
            "django_timezone": settings.TIME_ZONE,
            "has_running_job": has_running_job,
        },
    )


@login_required
@require_POST
def equipment_backup(request, pk: int):
    equipment = get_object_or_404(Equipment, pk=pk)
    equipment_host = None
    slug = equipment.equipment_type.slug
    if is_f5_ha_slug(slug):
        host_qs = EquipmentHost.objects.filter(equipment=equipment)
        if not host_qs.exists():
            messages.error(
                request,
                "Aucun nœud de cluster F5 configuré (administration → hosts de management).",
            )
            return redirect("equipment_detail", pk=equipment.pk)
    elif is_f5_standalone_slug(slug):
        host_qs = EquipmentHost.objects.filter(equipment=equipment).order_by(
            "sort_order",
            "pk",
        )
        if not host_qs.exists():
            messages.error(
                request,
                "Aucun host de management configuré (administration → hosts de management).",
            )
            return redirect("equipment_detail", pk=equipment.pk)
        if host_qs.count() == 1:
            equipment_host = host_qs.first()
        else:
            raw_host_id = request.POST.get("equipment_host_id", "").strip()
            if not raw_host_id.isdigit():
                messages.error(request, "Host requis.")
                return redirect("equipment_detail", pk=equipment.pk)
            equipment_host = get_object_or_404(host_qs, pk=int(raw_host_id))
    elif slug != "ddos":
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
    if slug == "nitrokey" or is_f5_family_slug(slug):
        credentials_mode = request.POST.get("credentials_mode", "default").strip().lower()
        if credentials_mode == "custom":
            username = request.POST.get("api_username", "").strip()
            password = request.POST.get("api_password", "")
            if not username or not password:
                messages.error(request, "Identifiants API personnalisés requis.")
                return redirect("equipment_detail", pk=equipment.pk)
            credentials = {"username": username, "password": password}
        elif slug == "nitrokey" and not default_nethsm_credentials_configured():
            messages.error(
                request,
                "Identifiants NetHSM par défaut non configurés sur le serveur (.env).",
            )
            return redirect("equipment_detail", pk=equipment.pk)
        elif is_f5_family_slug(slug) and not default_f5_credentials_configured():
            messages.error(
                request,
                "Identifiants SSH F5 par défaut non configurés sur le serveur (.env).",
            )
            return redirect("equipment_detail", pk=equipment.pk)

    job = BackupJob.objects.create(
        equipment=equipment,
        equipment_host=equipment_host,
        triggered_by=request.user,
        trigger=BackupJob.Trigger.MANUAL,
        status=BackupJob.Status.RUNNING,
    )
    logger.info(
        "Manual backup queued job_id=%s equipment_id=%s slug=%s user=%s",
        job.pk,
        equipment.pk,
        slug,
        request.user.username,
    )
    run_backup_job_async(job.pk, credentials=credentials)
    messages.info(
        request,
        "Sauvegarde démarrée — suivez la progression dans l'historique ci-dessous.",
    )
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


@login_required
@require_GET
def equipment_jobs_json(request, pk: int):
    equipment = get_object_or_404(Equipment, pk=pk)
    return JsonResponse(jobs_history_payload(equipment))
