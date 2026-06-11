from __future__ import annotations

from django import forms

from .models import BackupSchedule, Equipment, EquipmentHost
from .f5_credentials import default_f5_credentials_configured
from .nethsm_credentials import default_nethsm_credentials_configured


class BackupScheduleForm(forms.ModelForm):
    class Meta:
        model = BackupSchedule
        fields = (
            "is_enabled",
            "frequency",
            "run_time",
            "weekday",
            "day_of_month",
            "equipment_host",
        )
        widgets = {
            "run_time": forms.TimeInput(
                attrs={"type": "time", "class": "form-control"},
            ),
            "frequency": forms.Select(attrs={"class": "form-select js-schedule-frequency"}),
            "weekday": forms.Select(attrs={"class": "form-select js-schedule-weekday"}),
            "day_of_month": forms.NumberInput(
                attrs={"class": "form-control js-schedule-dom", "min": 1, "max": 28},
            ),
            "equipment_host": forms.Select(attrs={"class": "form-select js-schedule-host"}),
            "is_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *, equipment: Equipment, **kwargs):
        super().__init__(**kwargs)
        self.equipment = equipment
        host_qs = EquipmentHost.objects.filter(equipment=equipment).order_by(
            "sort_order",
            "pk",
        )
        self.fields["equipment_host"].queryset = host_qs
        self.fields["equipment_host"].required = False
        self.fields["equipment_host"].empty_label = "Premier host disponible"

        slug = equipment.equipment_type.slug
        if slug == "ddos":
            self.fields["equipment_host"].widget = forms.HiddenInput()
        elif not host_qs.exists():
            self.fields["equipment_host"].widget = forms.HiddenInput()
        elif host_qs.count() == 1:
            self.fields["equipment_host"].initial = host_qs.first().pk
            self.fields["equipment_host"].widget = forms.HiddenInput()

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("is_enabled"):
            return cleaned

        frequency = cleaned.get("frequency")
        if frequency == BackupSchedule.Frequency.WEEKLY and cleaned.get("weekday") is None:
            self.add_error("weekday", "Choisissez un jour de la semaine.")

        if frequency == BackupSchedule.Frequency.MONTHLY:
            dom = cleaned.get("day_of_month")
            if dom is None or dom < 1 or dom > 28:
                self.add_error("day_of_month", "Jour du mois entre 1 et 28.")

        slug = self.equipment.equipment_type.slug
        if slug == "nitrokey" and not default_nethsm_credentials_configured():
            raise forms.ValidationError(
                "Les sauvegardes planifiées Nitrokey nécessitent les identifiants "
                "par défaut du serveur (NITROKEY_NETHSM_* dans .env)."
            )
        if slug == "f5" and not default_f5_credentials_configured():
            raise forms.ValidationError(
                "Les sauvegardes planifiées F5 nécessitent les identifiants "
                "par défaut du serveur (F5_SSH_* dans .env)."
            )

        if self.equipment.equipment_type.slug != "ddos":
            host_qs = self.fields["equipment_host"].queryset
            if not host_qs.exists():
                raise forms.ValidationError("Aucun host configuré pour cet équipement.")
            if host_qs.count() > 1 and not cleaned.get("equipment_host"):
                self.add_error("equipment_host", "Sélectionnez un host pour la planification.")

        return cleaned
