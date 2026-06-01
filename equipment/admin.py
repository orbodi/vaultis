from django.contrib import admin
from django.db.models import Count, Max, Prefetch
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import BackupJob, Equipment, EquipmentHost, EquipmentType


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
    fields = (
        "status",
        "equipment_host",
        "started_at",
        "finished_at",
        "triggered_by",
        "message_short",
    )
    readonly_fields = (
        "status",
        "equipment_host",
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
            .select_related("triggered_by", "equipment_host")
            .order_by("-started_at")
        )


class EquipmentHostInline(admin.TabularInline):
    model = EquipmentHost
    extra = 1
    min_num = 0
    ordering = ("sort_order", "pk")
    fields = ("label", "address", "sort_order")
    show_change_link = True
    verbose_name = "Host de management"
    verbose_name_plural = "Hosts de management"


@admin.register(EquipmentHost)
class EquipmentHostAdmin(admin.ModelAdmin):
    list_display = ("address", "label", "equipment", "equipment_type_name", "sort_order")
    list_display_links = ("address",)
    list_filter = ("equipment__equipment_type", "equipment")
    search_fields = ("address", "label", "equipment__name")
    ordering = ("equipment__name", "sort_order", "pk")
    autocomplete_fields = ("equipment",)
    fieldsets = (
        (
            None,
            {
                "fields": ("equipment", "label", "address", "sort_order"),
                "description": (
                    "FQDN ou IP de management. Le libellé apparaît dans le sélecteur "
                    "de la fiche équipement."
                ),
            },
        ),
    )

    @admin.display(description="Type d’équipement", ordering="equipment__equipment_type__name")
    def equipment_type_name(self, obj):
        return obj.equipment.equipment_type.name

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .select_related("equipment", "equipment__equipment_type")
        )


@admin.register(Equipment)
class EquipmentAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "equipment_type",
        "hosts_summary",
        "last_backup_column",
        "updated_at",
    )
    list_display_links = ("name",)
    list_filter = ("equipment_type", "created_at", "updated_at")
    search_fields = ("name", "hosts__address", "hosts__label")
    ordering = ("name",)
    date_hierarchy = "created_at"
    autocomplete_fields = ("equipment_type",)
    readonly_fields = ("created_at", "updated_at", "last_backup_detail")
    inlines = (EquipmentHostInline, BackupJobInline)
    fieldsets = (
        (
            "Identification",
            {
                "fields": ("name", "equipment_type"),
                "description": (
                    "Ajoutez un ou plusieurs hosts de management dans la section ci-dessous "
                    "(libellé, adresse, ordre d’affichage)."
                ),
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

    @admin.display(description="Hosts")
    def hosts_summary(self, obj):
        if not obj.pk:
            return "—"
        all_hosts = list(obj.hosts.all())
        if not all_hosts:
            return format_html('<span style="color:#94a3b8;">—</span>')
        if len(all_hosts) <= 2:
            return ", ".join(h.address for h in all_hosts)
        return ", ".join(h.address for h in all_hosts[:2]) + f" (+{len(all_hosts) - 2})"

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
        return (
            super()
            .get_queryset(request)
            .select_related("equipment_type")
            .prefetch_related(
                Prefetch(
                    "hosts",
                    queryset=EquipmentHost.objects.order_by("sort_order", "pk"),
                )
            )
        )

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
        "backup_host",
        "status_badge",
        "started_at",
        "finished_at",
        "triggered_by",
    )
    list_display_links = ("id", "equipment")
    list_filter = ("status", "equipment__equipment_type", "started_at")
    search_fields = (
        "equipment__name",
        "equipment_host__address",
        "equipment_host__label",
        "message",
    )
    ordering = ("-started_at",)
    date_hierarchy = "started_at"
    autocomplete_fields = ("equipment", "triggered_by")
    readonly_fields = (
        "equipment",
        "equipment_host",
        "status",
        "message",
        "started_at",
        "finished_at",
        "triggered_by",
    )

    fieldsets = (
        (None, {"fields": ("equipment", "equipment_host", "status", "triggered_by")}),
        ("Résultat", {"fields": ("message", "started_at", "finished_at")}),
    )

    @admin.display(description="Type")
    def equipment_type(self, obj):
        return obj.equipment.equipment_type.name

    @admin.display(description="Host cible")
    def backup_host(self, obj):
        if obj.equipment_host_id:
            return obj.equipment_host.address
        return format_html('<span style="color:#94a3b8;">—</span>')

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
            .select_related(
                "equipment",
                "equipment__equipment_type",
                "equipment_host",
                "triggered_by",
            )
        )


admin.site.site_header = "Device backup — administration"
admin.site.site_title = "Admin"
admin.site.index_title = "Gestion des équipements et des sauvegardes"
