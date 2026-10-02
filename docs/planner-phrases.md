# Planner phrases — contratto e workflow

> Stato: nota architetturale permanente. Descrive il contratto introdotto
> dalla mini-refactor delle Planner phrases: `src/planner/phrases.py` +
> `tests/test_planner_phrases.py`. Non cambia comportamenti, solo li rende
> espliciti e verificabili.

## 1. Concetto

Il Planner **non costruisce mai testo UI**. Produce riferimenti, la UI li
renderizza:

```text
domain/planner → PhraseRef oppure kind/reason legacy → mapping → T(key, params)
```

Tre forme coesistono per compatibilità, con ruoli diversi:

| Forma | Cos'è | Dove nasce | Chi la converte |
|---|---|---|---|
| `PhraseRef(key, params, origin)` | riferimento tipizzato a frase | `narrative.py`, `phrases.py` | UI: `T(ref.key, **ref.params)` |
| `kind` | stringa da vocabolario chiuso (`"capacity"`, `"moved"`, `"scheduled"`…) | `diagnostics.py`, `replan.py`, `decisions.py` | UI: `phrase_for(kind, family, detail)` |
| `reason = (key, params)` legacy | tupla grezza merito/capacità | `explain.py` (invariato per compat) | usata direttamente come `(key, params)` |

`PhraseRef` è un `NamedTuple` piccolo senza logica di rendering;
`tuple(ref)[:2]` dà compat `(key, params)`. `origin`
(`story`/`blocker`/`replan`/`decision`) è diagnostica developer-only.

## 2. Le quattro famiglie

| Famiglia | Produttore | Mapping | Renderer |
|---|---|---|---|
| `story` | `narrative.explain_decision/proposed` → `PhraseRef(…, "story")` (stessa selezione di sempre) | nessuno (è già chiave) | `views.py` Why-card: `T(story.key, **story.params)` |
| `blocker` | `diagnostics.py` → `kind` + `detail` (mai chiavi) | `phrase_for(kind, "blocked-line"/"blocked-frag", detail)` | `_blocked_line` / `_cause_text` in `views.py` |
| `replan` | `replan.py` → `kind` (`KEPT`/`MOVED`/`DROPPED`/`ADDED`) | `phrase_for(kind, "replan")` in `plan.py` + `cli.py` | `T(ref.key, …)` nei rispettivi loop righe |
| `decision` | `decisions.py` → stati | `phrase_for(kind, "decision")` via `_decision_label()` in `views.py` | Why-card |

`phrase_for` solleva `KeyError` su kind ignoto o detail mancante (errore
programmatore); ogni call-site UI lo gestisce con fallback legacy (`None`
o etichetta di default). Eccezione documentata: `_NOSLOT_MERIT` in
`views.py` resta un mapping parziale reason→frag intenzionale (chiave
ignota → `None` → rendering legacy, mai generico).

## 3. Come aggiungere una nuova frase

1. **Scegli la famiglia**: motivo di merito → `explain.py`; story →
   `narrative.py`; blocco/riga replan/etichetta → tabella `phrase_for`.
2. **Aggiungi `it` + `en`** in `src/lang.py` (parità imposta da
   `test_parita_chiavi`).
3. **Collega il mapping** in `src/planner/phrases.py` se è un kind nuovo
   (una riga di tabella); niente da fare se riusi kind/chiavi esistenti.
4. **Params**: dichiara solo `{x}` usati davvero; il test placeholder
   verifica che siano forniti.
5. **Aggiungi il test**: kind nuovo → riga in
   `tests/test_planner_phrases.py` (fallisce da solo se manca chiave o
   param); story nuova → caso in `tests/test_narrative.py`.
6. **Verifica**: `pytest tests/test_planner_phrases.py tests/test_lang.py`
   + la suite della famiglia toccata.

## 4. Regole architetturali

* Mai `T()` dentro `src/planner/` (solo chiavi e kind).
* Mai costruire chiavi i18n dinamicamente nella UI (`T(f"…{var}")`
  vietato per il Planner; restano solo `help_l*`/`workflow_s*`, bounded e
  testati).
* Usare `phrase_for()` per i vocabolari chiusi; non duplicare `kind → key`.
* `_NOSLOT_MERIT` resta parziale per disegno (vedi §2).
* Non convertire le tuple legacy di `explain.py` (compat scoring/
  partition/capacity/test).
* Non passare testo tradotto nel Planner; non mettere logica di
  rendering in `PhraseRef`.

## 5. Esempio: nuova riga replan `postponed`

Catalogo (`src/lang.py`, entrambe le lingue):

```python
"cli_replan_postponed": "Rinviati:",   # it
"cli_replan_postponed": "Postponed:",  # en
```

Mapping (una riga in `src/planner/phrases.py`, tabella `_REPLAN`):

```python
"postponed": "cli_replan_postponed",
```

Il `kind` `"postponed"` deve esistere dal lato dominio (es. costante in
`replan.py`); rendering invariato nei due loop esistenti:

```python
ref = phrase_for(kind, "replan")
print(T(ref.key, **ref.params))   # cli.py; analogo in screens/plan.py
```

Test (estende il loop esistente in `tests/test_planner_phrases.py`):
il kind attraversa `phrase_for → key → catalogo it/en` da solo; se la
chiave o un param manca, il test fallisce prima del merge.
