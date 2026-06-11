"""F5-DN1 — sauvegarde UCS directe (sans cluster HA)."""

from equipment.f5_variant import F5_DN1

from .f5_standalone import StandaloneF5Adapter


class Adapter(StandaloneF5Adapter):
    variant = F5_DN1
