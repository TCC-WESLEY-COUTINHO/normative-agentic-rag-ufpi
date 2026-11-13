"""Explicit corpus scope; missing metadata never implies graduation."""

from typing import Literal

Sector = Literal["graduacao", "pos_graduacao"]


def validate_sector(sector: str | None) -> str | None:
    if sector is not None and sector not in ("graduacao", "pos_graduacao"):
        raise ValueError(
            "Setor deve ser graduacao ou pos_graduacao; ausente significa desconhecido."
        )
    return sector


def source_scopes(sector=None, source=None, sources=None):
    validate_sector(sector)
    if source is not None and sources is not None:
        raise ValueError("Use fonte ou fontes, não ambos.")
    if sources is not None and (not sources or any(not s.strip() for s in sources)):
        raise ValueError("fontes deve conter nomes não vazios.")
    if source is not None and not source.strip():
        raise ValueError("fonte não pode ser vazia.")
    names = list(dict.fromkeys(sources)) if sources is not None else [source]
    return [
        dict(**({"setor": sector} if sector else {}), **({"fonte": n} if n else {})) for n in names
    ]
