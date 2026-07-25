"""
FIT Analyzer per tesi Gaia - Streamlit UI.

Uso locale:
    streamlit run app.py

Deploy: Streamlit Community Cloud (share.streamlit.io) da repo GitHub pubblico.
"""
from __future__ import annotations

import io
import json
from datetime import datetime

import pandas as pd
import streamlit as st

from analyzer import Tratto, analyze_fit, default_soglie, deg_to_semi, semi_to_deg
import storage

st.set_page_config(page_title="FIT Analyzer - Tesi Gaia", page_icon="🚴", layout="wide")


def _check_login() -> bool:
    """Login semplice via st.secrets['users']. Se non ci sono secrets, l'app è aperta."""
    try:
        users = st.secrets.get("users", {})
    except Exception:
        users = {}
    if not users:
        return True
    if st.session_state.get("auth_ok"):
        return True
    st.title("🚴 FIT Analyzer")
    st.write("Login richiesto.")
    with st.form("login"):
        u = st.text_input("Username")
        p = st.text_input("Password", type="password")
        ok = st.form_submit_button("Entra")
    if ok:
        if users.get(u) == p:
            st.session_state["auth_ok"] = True
            st.session_state["auth_user"] = u
            st.rerun()
        else:
            st.error("Credenziali non valide.")
    return False


if not _check_login():
    st.stop()

st.title("🚴 FIT Analyzer - Tesi Gaia")
st.caption("Carica uno o più file .fit, calcola in un colpo TUTTE le soglie W/kg per TUTTI i tratti.")

# ────────────────────────── ARCHIVIO SIDEBAR ──────────────────────────
with st.sidebar:
    st.divider()
    if storage.is_enabled():
        st.subheader("📚 Archivio")
        try:
            corridori_in_archivio = storage.list_corridori()
            st.caption(f"{len(corridori_in_archivio)} corridori salvati")
            with st.expander("Vedi elenco"):
                for c in corridori_in_archivio:
                    st.write(f"• {c}")
            auto_save = st.checkbox("Salva automaticamente le analisi in archivio", value=True)
        except Exception as e:
            st.warning(f"Archivio non raggiungibile: {e}")
            auto_save = False
    else:
        st.info("Archivio non configurato (aggiungi `[storage]` nei secrets).")
        auto_save = False
    st.session_state["auto_save"] = auto_save

# ────────────────────────── SIDEBAR ──────────────────────────
with st.sidebar:
    st.header("Parametri globali")
    peso_kg = st.number_input("Peso corridore (kg)", 40.0, 100.0, 72.0, 0.5)
    rolling_s = st.number_input("Media mobile (secondi)", 1, 300, 3, 1,
                                help="Default 3 sec — è quello che Gaia usa in App4.3.")

    st.subheader("Soglie W/kg")
    modo_soglie = st.radio(
        "Come definire le soglie",
        ["Range (default 3.5→8, step 0.5)", "Custom"],
        index=0,
    )
    if modo_soglie.startswith("Range"):
        c1, c2, c3 = st.columns(3)
        s_min = c1.number_input("Min", 1.0, 10.0, 3.5, 0.5)
        s_max = c2.number_input("Max", 1.0, 15.0, 8.0, 0.5)
        s_step = c3.number_input("Step", 0.1, 1.0, 0.5, 0.1)
        soglie = [round(x, 2) for x in
                  __import__("numpy").arange(s_min, s_max + 0.0001, s_step).tolist()]
    else:
        soglie_str = st.text_input("Soglie separate da virgola", "3.5,4,4.5,5,5.5,6,6.5,7,7.5,8")
        soglie = [float(x.strip()) for x in soglie_str.split(",") if x.strip()]

    st.write("Soglie attive:", soglie)

    st.divider()
    st.subheader("Formato coordinate")
    formato_coord = st.radio(
        "I lat/long nei tratti sono in:",
        ["Gradi decimali (es. 45.6789)", "Semicircles (formato .fit)"],
        index=0,
    )
    tol_semi = st.number_input("Tolleranza GPS (semicircles)", 10, 100000, 100, 10,
                               help="La soglia di App4.3 era 100. Aumenta se i tratti non 'agganciano' i record.")

# ────────────────────────── PRESET GARE ──────────────────────────
PRESET_PATH = "presets_gare.json"


@st.cache_data
def load_presets():
    try:
        with open(PRESET_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


presets = load_presets()

# ────────────────────────── METADATA & TRATTI ──────────────────────────
st.header("1. Metadata gara")

c1, c2, c3 = st.columns(3)
gara_default = list(presets.keys())[0] if presets else "Milano-Sanremo"
gara_names = list(presets.keys()) + ["-- Nuova gara --"]
gara_sel = c1.selectbox("Gara", gara_names, index=0)
if gara_sel == "-- Nuova gara --":
    gara = c1.text_input("Nome nuova gara")
else:
    gara = gara_sel
anno = c2.number_input("Anno", 2000, 2030, 2025, 1)
corridore_default = c3.text_input("Corridore (fallback)", "Corridore1",
                                  help="Usato se il nome file non finisce con '__nomecorridore.fit'")

st.header("2. Tratti (4 per gara)")

# recupera tratti dal preset selezionato
preset_tratti = presets.get(gara_sel, {}).get("tratti", []) if gara_sel in presets else []

tratti = []
tabs = st.tabs([f"Tratto {i+1}" for i in range(4)])
for i, tab in enumerate(tabs):
    with tab:
        default = preset_tratti[i] if i < len(preset_tratti) else {}
        nome = st.text_input(f"Nome tratto {i+1}", default.get("nome", f"Tratto {i+1}"), key=f"n{i}")
        cc = st.columns(4)
        lat_s = cc[0].number_input(f"lat start", value=float(default.get("lat_start", 0.0)),
                                   format="%.6f", key=f"la1{i}")
        lat_e = cc[1].number_input(f"lat end", value=float(default.get("lat_end", 0.0)),
                                   format="%.6f", key=f"la2{i}")
        lon_s = cc[2].number_input(f"long start", value=float(default.get("long_start", 0.0)),
                                   format="%.6f", key=f"lo1{i}")
        lon_e = cc[3].number_input(f"long end", value=float(default.get("long_end", 0.0)),
                                   format="%.6f", key=f"lo2{i}")

        if formato_coord.startswith("Gradi"):
            la_s, la_e = deg_to_semi(lat_s), deg_to_semi(lat_e)
            lo_s, lo_e = deg_to_semi(lon_s), deg_to_semi(lon_e)
        else:
            la_s, la_e = int(lat_s), int(lat_e)
            lo_s, lo_e = int(lon_s), int(lon_e)

        tratti.append(Tratto(
            nome=nome, lat_start=la_s, lat_end=la_e,
            long_start=lo_s, long_end=lo_e, gps_tolerance=int(tol_semi),
        ))

# ────────────────────────── UPLOAD & ANALISI ──────────────────────────
st.header("3. Upload file .fit")
st.caption("Puoi caricare più file insieme. Nome file consigliato: `qualsiasi__Cognome.fit` "
           "(il pezzo dopo `__` diventa il nome del corridore).")

uploads = st.file_uploader("Trascina qui i file .fit", type=["fit"], accept_multiple_files=True)

if st.button("🚀 Analizza tutto", type="primary", disabled=not uploads):
    all_dfs = []
    prog = st.progress(0, text="Analisi in corso…")
    for i, up in enumerate(uploads, start=1):
        # inferisci nome corridore da filename: `qualsiasi__Cognome.fit`
        stem = up.name.rsplit(".", 1)[0]
        if "__" in stem:
            corridore_name = stem.split("__", 1)[1]
        else:
            corridore_name = corridore_default

        try:
            df = analyze_fit(
                fit_bytes=up.read(),
                corridore=corridore_name,
                gara=gara or "N/A",
                anno=int(anno),
                peso_kg=float(peso_kg),
                tratti=tratti,
                soglie_wkg=soglie,
                rolling_window_s=int(rolling_s),
            )
            if df.empty:
                st.warning(f"⚠️ {up.name}: nessun record valido nel file.")
            else:
                all_dfs.append(df)
                st.success(f"✅ {up.name} → {corridore_name} ({len(df)} righe)")
        except Exception as e:
            st.error(f"❌ {up.name}: {e}")
        prog.progress(i / len(uploads), text=f"{i}/{len(uploads)}")

    if all_dfs:
        master = pd.concat(all_dfs, ignore_index=True)
        st.session_state["master"] = master

        # auto-save in archivio (una entry per corridore per analisi)
        if st.session_state.get("auto_save") and storage.is_enabled():
            saved = 0
            for cor, sub in master.groupby("corridore"):
                try:
                    storage.save_analisi(cor, sub, note=f"upload {datetime.now():%Y-%m-%d %H:%M}")
                    saved += 1
                except Exception as e:
                    st.warning(f"❌ archivio '{cor}': {e}")
            if saved:
                st.success(f"💾 Salvato in archivio: {saved} corridore/i")

if "master" in st.session_state:
    st.header("4. Risultati")
    df = st.session_state["master"]
    st.dataframe(df, use_container_width=True, hide_index=True)

    # ───────── GRAFICI ─────────
    st.header("5. Grafici")
    tab_g1, tab_g2, tab_g3, tab_g4 = st.tabs([
        "Superamenti per soglia",
        "Secondi sopra soglia",
        "Confronto corridori",
        "Confronto tratti",
    ])

    with tab_g1:
        st.caption("Numero di superamenti soglia per ogni tratto, al variare della soglia W/kg.")
        # una serie per tratto, per corridore selezionato
        c1, c2 = st.columns(2)
        cor_sel = c1.selectbox("Corridore", sorted(df["corridore"].unique()), key="g1_cor")
        gara_sel_g = c2.selectbox("Gara-Anno", sorted(df.assign(g=df["gara"]+" "+df["anno"].astype(str))["g"].unique()), key="g1_g")
        gara_name, anno_name = gara_sel_g.rsplit(" ", 1)
        sub = df[(df["corridore"] == cor_sel) & (df["gara"] == gara_name) & (df["anno"] == int(anno_name))]
        if not sub.empty:
            pivot = sub.pivot_table(index="soglia_wkg", columns="tratto", values="n_superamenti", aggfunc="sum")
            st.line_chart(pivot, height=400)
            st.bar_chart(pivot, height=400)
        else:
            st.info("Nessun dato per la selezione.")

    with tab_g2:
        st.caption("Secondi totali sopra soglia per tratto.")
        c1, c2 = st.columns(2)
        cor_sel2 = c1.selectbox("Corridore", sorted(df["corridore"].unique()), key="g2_cor")
        gara_sel2 = c2.selectbox("Gara-Anno", sorted(df.assign(g=df["gara"]+" "+df["anno"].astype(str))["g"].unique()), key="g2_g")
        gara_name2, anno_name2 = gara_sel2.rsplit(" ", 1)
        sub2 = df[(df["corridore"] == cor_sel2) & (df["gara"] == gara_name2) & (df["anno"] == int(anno_name2))]
        if not sub2.empty:
            pivot2 = sub2.pivot_table(index="soglia_wkg", columns="tratto", values="secondi_sopra", aggfunc="sum")
            st.area_chart(pivot2, height=400)
        else:
            st.info("Nessun dato per la selezione.")

    with tab_g3:
        st.caption("Confronto tra corridori sulla stessa soglia W/kg.")
        c1, c2 = st.columns(2)
        soglia_sel = c1.selectbox("Soglia W/kg", sorted(df["soglia_wkg"].unique()), key="g3_s")
        metrica = c2.selectbox("Metrica", ["n_superamenti", "secondi_sopra", "media_wkg"], key="g3_m")
        sub3 = df[df["soglia_wkg"] == soglia_sel]
        if not sub3.empty:
            pivot3 = sub3.pivot_table(index="corridore", columns="tratto", values=metrica, aggfunc="sum")
            st.bar_chart(pivot3, height=400)
            st.dataframe(pivot3, use_container_width=True)
        else:
            st.info("Nessun dato per la selezione.")

    with tab_g4:
        st.caption("Confronto tra tratti (media dei corridori) per soglia.")
        metrica2 = st.selectbox("Metrica", ["n_superamenti", "secondi_sopra", "media_wkg"], key="g4_m")
        pivot4 = df.pivot_table(index="soglia_wkg", columns="tratto", values=metrica2, aggfunc="mean")
        st.line_chart(pivot4, height=400)
        st.dataframe(pivot4.round(2), use_container_width=True)

    # download CSV + Excel
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Scarica CSV",
        csv,
        file_name=f"analisi_{datetime.now():%Y%m%d_%H%M}.csv",
        mime="text/csv",
    )

    # Excel con una sheet per corridore-gara-anno + master
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="master", index=False)
        for (cor, ga, an), sub in df.groupby(["corridore", "gara", "anno"]):
            sheet = f"{cor}_{ga}_{an}"[:31]
            sub.to_excel(writer, sheet_name=sheet, index=False)
    st.download_button(
        "⬇️ Scarica Excel (con sheet per corridore)",
        buf.getvalue(),
        file_name=f"analisi_{datetime.now():%Y%m%d_%H%M}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

# ────────────────────────── ARCHIVIO ──────────────────────────
if storage.is_enabled():
    st.divider()
    st.header("📚 Cronologia archivio")
    st.caption("Tutte le analisi salvate. Filtro per corridore, apri per vedere i dati.")
    try:
        corridori = storage.list_corridori()
    except Exception as e:
        st.warning(f"Archivio non raggiungibile: {e}")
        corridori = []

    if not corridori:
        st.info("Archivio vuoto: fai una prima analisi con auto-save attivo.")
    else:
        cor_sel = st.selectbox("Corridore", corridori, key="arch_cor")
        data = storage.load_corridore(cor_sel)
        if data:
            analisi = data.get("analisi", [])
            st.caption(f"**{len(analisi)}** analisi archiviate per **{cor_sel}**")
            for entry in reversed(analisi):
                header = f"{entry.get('gara','?')} {entry.get('anno','?')} — {entry.get('creata_il','')} — id `{entry['id']}`"
                with st.expander(header):
                    df_e = storage.analisi_as_df(entry)
                    st.dataframe(df_e, use_container_width=True, hide_index=True)
                    csv_e = df_e.to_csv(index=False).encode("utf-8")
                    c1, c2 = st.columns([1, 1])
                    c1.download_button("⬇️ Scarica CSV", csv_e,
                                       file_name=f"{cor_sel}_{entry['id']}.csv",
                                       mime="text/csv", key=f"dl_{entry['id']}")
                    if c2.button("🗑️ Elimina", key=f"rm_{entry['id']}"):
                        storage.delete_analisi(cor_sel, entry["id"])
                        st.rerun()

# ────────────────────────── GUIDA ──────────────────────────
st.divider()
with st.expander("📖 Guida di utilizzo (clicca per aprire)", expanded=False):
    try:
        with open("guida.md", encoding="utf-8") as f:
            st.markdown(f.read())
    except FileNotFoundError:
        st.info("Guida non trovata (file guida.md).")
