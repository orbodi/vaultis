from django.contrib import admin
from django.db.models import Count, Max
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import BackupJob, Equipment, EquipmentType


@admin.register(EquipmentType)
class EquipmentTypeAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "adapter_key", "equipment_count")
    list_display_links = ("name", "slug")
    search_fields = ("name", "slug", "adapter_key", "description")
    ordering = ("name",)
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "slug"),
                "description": "Le slug sert d’identifiant technique (URL, adaptateurs).",
            },
        ),
        (
            "Intégration API",
            {
                "fields": ("adapter_key", "description"),
                "description": "Chemin Python du module qui appellera l’API fabricant.",
            },
        ),
    )

    @admin.display(description="Nb équipements", ordering="equipment_count")
    def equipment_count(self, obj):
        return getattr(obj, "equipment_count", obj.equipments.count())

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.annotate(equipment_count=Count("equipments", distinct=True))


class BackupJobInline(admin.TabularInline):
    model = BackupJob
    extra = 0
    can_delete = False
    max_num = 30
    show_change_link = True
    fields = ("status", "started_at", "finished_at", "triggered_by", "message_short")
    readonly_fields = (
        "status",
        "started_at",
        "finished_at",
        "triggered_by",
        "message_short",
    )

    @admin.display(description="Message")
    def message_short(self, obj):
        if not obj.pk or not obj.message:
            return "—"
        text = obj.message.strip()
        if len(text) > 80:
            return text[:77] + "…"
        return text

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("triggered_by")
            .order_by("-started_at")
        )


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "equipment_type",
        "host",
        "last_backup_column",
        "updated_at",
    )
    list_display_links = ("name",)
    list_filter = ("equipment_type", "created_at", "updated_at")
    search_fields = ("name", "host")
    ordering = ("name",)
    date_hierarchy = "created_at"
    autocomplete_fields = ("equipment_type",)
    readonly_fields = ("created_at", "updated_at", "last_backup_detail")
    inlines = (BackupJobInline,)
    fieldsets = (
        (
            "Identification",
            {
                "fields": ("name", "equipment_type"),
            },
        ),
        (
            "Connexion",
            {
                "fields": ("host",),
                "description": "FQDN ou IP de management utilisée par les adaptateurs API.",
            },
        ),
        (
            "Paramètres supplémentaires",
            {
                "fields": ("extra",),
                "description": "JSON libre (références, partition F5, groupe Panorama, etc.).",
            },
        ),
        (
            "Suivi",
            {
                "fields": ("created_at", "updated_at", "last_backup_detail"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="Dernière sauvegarde")
    def last_backup_column(self, obj):
        job = getattr(obj, "_last_job", None)
        if job is None:
            job = obj.last_backup_job()
        if not job:
            return format_html('<span style="color:#94a3b8;">—</span>')
        color = {
            BackupJob.Status.SUCCESS: "#0f766e",
            BackupJob.Status.FAILED: "#b91c1c",
            BackupJob.Status.RUNNING: "#b45309",
            BackupJob.Status.PENDING: "#64748b",
        }.get(job.status, "#64748b")
        label = job.get_status_display()
        return format_html(
            '<span style="color:{};font-weight:600;">{}</span><br>'
            '<span style="color:#64748b;font-size:11px;">{}</span>',
            color,
            label,
            job.started_at.strftime("%d/%m/%Y %H:%M"),
        )

    @admin.display(description="Détail dernier job")
    def last_backup_detail(self, obj):
        if not obj.pk:
            return "—"
        job = obj.last_backup_job()
        if not job:
            return "Aucune sauvegarde enregistrée."
        lines = [
            f"Statut : {job.get_status_display()}",
            f"Début : {job.started_at}",
            f"Fin : {job.finished_at or '—'}",
            f"Utilisateur : {job.triggered_by or '—'}",
            f"Message : {job.message or '—'}",
        ]
        return mark_safe("<br>".join(lines))

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("equipment_type")

    def changelist_view(self, request, extra_context=None):
        response = super().changelist_view(request, extra_context=extra_context)
        try:
            cl = response.context_data["cl"]
        except (AttributeError, KeyError, TypeError):
            return response
        queryset = cl.result_list
        if not queryset:
            return response
        ids = [o.pk for o in queryset]
        latest_ids = (
            BackupJob.objects.filter(equipment_id__in=ids)
            .values("equipment_id")
            .annotate(mid=Max("id"))
        )
        id_map = {row["equipment_id"]: row["mid"] for row in latest_ids}
        jobs = {
            j.pk: j
            for j in BackupJob.objects.filter(pk__in=list(id_map.values())).select_related(
                "triggered_by"
            )
        }
        by_eq = {}
        for eq_id, jid in id_map.items():
            job = jobs.get(jid)
            if job:
                by_eq[eq_id] = job
        for obj in queryset:
            obj._last_job = by_eq.get(obj.pk)
        return response


@admin.register(BackupJob)
class BackupJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "equipment",
        "equipment_type",
        "status_badge",
        "started_at",
        "finished_at",
        "triggered_by",
    )
    list_display_links = ("id", "equipment")
    list_filter = ("status", "equipment__equipment_type", "started_at")
    search_fields = ("equipment__name", "equipment__host", "message")
    ordering = ("-started_at",)
    date_hierarchy = "started_at"
    autocomplete_fields = ("equipment", "triggered_by")
    readonly_fields = (
        "equipment",
        "status",
        "message",
        "started_at",
        "finished_at",
        "triggered_by",
    )

    fieldsets = (
        (None, {"fields": ("equipment", "status", "triggered_by")}),
        ("Résultat", {"fields": ("message", "started_at", "finished_at")}),
    )

    @admin.display(description="Type")
    def equipment_type(self, obj):
        return obj.equipment.equipment_type.name

    @admin.display(description="Statut")
    def status_badge(self, obj):
        colors = {
            BackupJob.Status.SUCCESS: "success",
            BackupJob.Status.FAILED: "danger",
            BackupJob.Status.RUNNING: "warning",
            BackupJob.Status.PENDING: "secondary",
        }
        css = colors.get(obj.status, "secondary")
        return format_html(
            '<span class="badge text-bg-{}">{}</span>',
            css,
            obj.get_status_display(),
        )

    def has_add_permission(self, request):
        return False

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("equipment", "equipment__equipment_type", "triggered_by")
        )


admin.site.site_header = "Device backup — administration"
admin.site.site_title = "Admin"
admin.site.index_title = "Gestion des équipements et des sauvegardes"
