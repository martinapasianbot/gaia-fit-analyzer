# FIT Analyzer - Tesi Gaia

Web app che sostituisce App4.3 di Gaia: carica file `.fit`, calcola in un colpo
tutte le soglie W/kg (3.5→8, step 0.5) per tutti i 4 tratti di ogni gara,
esporta un Excel pronto per la tesi.

## Quick start (locale)

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Apre <http://localhost:8501>.

## Deploy pubblico

Streamlit Community Cloud: <https://share.streamlit.io> → New app → repo GitHub → `app.py`.

## Struttura

- `app.py` — UI Streamlit
- `analyzer.py` — logica core (refactor di App4.3)
- `presets_gare.json` — coordinate dei 4 tratti per le 5 monumento (da confermare con Gaia)
- `requirements.txt`

## Cosa fa in più rispetto ad App4.3

- **Batch soglie in un solo passaggio** (non più un parameter set per soglia)
- **Multi-file upload** (30 file `.fit` insieme)
- **Preset gare persistiti** (le coordinate dei tratti si caricano da JSON)
- **Export Excel** con sheet per corridore + master aggregata
- **Zero installazione per Gaia**: apre un link nel browser
