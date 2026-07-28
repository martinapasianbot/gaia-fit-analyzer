"""
Analyzer core - refactor di App4.3.
Legge un file .fit, calcola in UN colpo tutte le soglie W/kg per tutti i tratti.

Uso:
    from analyzer import analyze_fit
    df = analyze_fit(fit_bytes, corridore="Pogacar", gara="Sanremo", anno=2025,
                     peso_kg=66, tratti=[...], soglie_wkg=[3.5, 4.0, ..., 8.0])
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from fitparse import FitFile


@dataclass
class Tratto:
    nome: str
    lat_start: float
    lat_end: float
    long_start: float
    long_end: float
    gps_tolerance: int = 100  # semicircles


SEMI_PER_DEG = 2**31 / 180.0


def deg_to_semi(deg: float) -> int:
    return int(round(deg * SEMI_PER_DEG))


def semi_to_deg(semi: int | float) -> float:
    return float(semi) / SEMI_PER_DEG


def _swap(a, b):
    return (a, b) if a <= b else (b, a)


def _fit_to_records_df(fit_bytes: bytes) -> pd.DataFrame:
    """Estrae i record 'record' del .fit in DataFrame con timestamp/lat/long/power/heart_rate/cadence."""
    fit = FitFile(io.BytesIO(fit_bytes))
    rows = []
    for msg in fit.get_messages("record"):
        d = {f.name: f.value for f in msg.fields}
        rows.append(d)
    df = pd.DataFrame(rows)
    # normalizza colonne
    for col in ("timestamp", "position_lat", "position_long", "power",
                "heart_rate", "cadence", "altitude", "speed", "distance"):
        if col not in df.columns:
            df[col] = np.nan
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).reset_index(drop=True)
    return df


def _mark_inside(df: pd.DataFrame, tratto: Tratto) -> pd.Series:
    """Ritorna una Series bool: True se lat/long del record stanno nel bounding box del tratto (con tolleranza)."""
    lat_lo, lat_hi = _swap(tratto.lat_start, tratto.lat_end)
    lon_lo, lon_hi = _swap(tratto.long_start, tratto.long_end)
    tol = tratto.gps_tolerance
    lat_ok = df["position_lat"].between(lat_lo - tol, lat_hi + tol)
    lon_ok = df["position_long"].between(lon_lo - tol, lon_hi + tol)
    return lat_ok & lon_ok


def analyze_fit(
    fit_bytes: bytes,
    corridore: str,
    gara: str,
    anno: int,
    peso_kg: float,
    tratti: list[Tratto],
    soglie_wkg: Iterable[float],
    rolling_window_s: int = 30,
    min_run_seconds: int = 3,
) -> pd.DataFrame:
    """
    Ritorna un DataFrame con una riga per (tratto, soglia_wkg):
        corridore, gara, anno, tratto, soglia_wkg,
        n_superamenti, secondi_sopra, media_potenza_w, media_wkg,
        durata_tratto_s, campioni_tratto

    min_run_seconds: solo i run consecutivi sopra soglia di durata >= min_run_seconds
    vengono contati (n_superamenti e secondi_sopra). Spike più brevi vengono ignorati.
    """
    df = _fit_to_records_df(fit_bytes)
    if df.empty:
        return pd.DataFrame()

    # rolling mean sui watt (media mobile in secondi, assumendo 1 sample/s che è standard .fit)
    df["power"] = pd.to_numeric(df["power"], errors="coerce").fillna(0)
    df["power_rolling"] = df["power"].rolling(window=rolling_window_s, min_periods=1).mean()
    df["wkg_rolling"] = df["power_rolling"] / peso_kg

    soglie = sorted(set(round(float(s), 2) for s in soglie_wkg))
    out_rows = []

    for t in tratti:
        inside = _mark_inside(df, t)
        sub = df.loc[inside].copy()
        if sub.empty:
            for s in soglie:
                out_rows.append({
                    "corridore": corridore, "gara": gara, "anno": anno,
                    "tratto": t.nome, "soglia_wkg": s,
                    "n_superamenti": 0, "secondi_sopra": 0,
                    "media_potenza_w": np.nan, "media_wkg": np.nan,
                    "durata_tratto_s": 0, "campioni_tratto": 0,
                })
            continue

        durata_s = (sub["timestamp"].iloc[-1] - sub["timestamp"].iloc[0]).total_seconds()
        media_pw = float(sub["power_rolling"].mean())
        media_wkg = media_pw / peso_kg

        wkg = sub["wkg_rolling"].to_numpy()

        for s in soglie:
            over = (wkg > s).astype(int)
            # trova i run consecutivi (start/end index) di valori sopra soglia
            edges = np.diff(over, prepend=0, append=0)
            starts = np.where(edges == 1)[0]
            ends = np.where(edges == -1)[0]
            run_lengths = ends - starts  # secondi (1 sample/s)
            # filtro: contano solo i run di durata >= min_run_seconds
            valid = run_lengths >= int(min_run_seconds)
            n_sup = int(valid.sum())
            sec_sopra = int(run_lengths[valid].sum())
            out_rows.append({
                "corridore": corridore, "gara": gara, "anno": anno,
                "tratto": t.nome, "soglia_wkg": s,
                "n_superamenti": n_sup, "secondi_sopra": sec_sopra,
                "media_potenza_w": round(media_pw, 1),
                "media_wkg": round(media_wkg, 2),
                "durata_tratto_s": int(durata_s),
                "campioni_tratto": len(sub),
            })

    return pd.DataFrame(out_rows)


def default_soglie() -> list[float]:
    """3.5, 4.0, 4.5, ..., 8.0 W/kg"""
    return [round(x, 2) for x in np.arange(3.5, 8.5, 0.5)]
