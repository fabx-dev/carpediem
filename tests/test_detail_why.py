"""Why nel Detail M3: sezione da PlanningDecision, mai logica duplicata.

Decisione reale, evidence reale, motivo principale reale; non valutato ->
messaggio esplicito per stato; coerenza Planner/Detail a parita' di
(todos, today, hours); Esc e assenza dati senza crash.
"""

from datetime import datetime

from textual.widgets import Label

import src.planner.decisions as dec
from src.lang import T
from src.planner import Planner, decide
from src.screens.views import DetailScreen
from tests.conftest import (
    label_texts,
    make_app,
    make_todo,
    run,
    screen_texts,
    wait_for,
)

TODAY = "2026-09-10"


async def _open_detail(pilot, app, todo, today=TODAY, hours=6.0):
    app.push_screen(DetailScreen(todo, app.todos, today=today, hours=hours))
    await pilot.pause()
    await pilot.pause()
    assert type(app.screen).__name__ == "DetailScreen"


def _why_block_labels(screen, label_text, story_text):
    """Etichette della card Why fra decisione e Dettagli (struttura DOM).

    Invariante di gerarchia del Lotto 2: etichetta di decisione, POI una
    sola riga (la story) e subito la sezione Dettagli. Nessuna riga-bandiera
    in mezzo (overdue/mandatory/capacita' duplicati): e' il controllo
    strutturale che sostituisce le vecchie asserzioni negative su chiavi i18n
    rimosse, che sarebbero vacue perche' `T()` cade sul nome della chiave.

    Sul DOM e non su `screen_texts()`: quello joina le Label con uno spazio,
    quindi ogni riga finirebbe sulla stessa stringa e l'ordine sarebbe
    indistinguibile.
    """
    texts = label_texts(screen)
    i = next((n for n, t in enumerate(texts) if label_text in t), None)
    k = next((n for n, t in enumerate(texts) if T("why_sec_details") in t), None)
    assert i is not None, f"etichetta di decisione assente: {label_text!r}"
    assert k is not None and k > i, "sezione Dettagli assente o prima della decisione"
    between = texts[i + 1 : k]
    assert len(between) == 1, (
        f"fra decisione e Dettagli una sola riga (la story), trovate {between!r}"
    )
    assert story_text in between[0], f"riga intermedia non e' la story: {between[0]!r}"
    return between


def test_why_nessuna_riga_bandiera_in_mezzo_pianificato(tmp_files):
    """Fra etichetta di decisione e Dettagli c'e' solo la story, niente bandiere."""

    def t():
        async def inner():
            app = make_app(
                [
                    make_todo(
                        "A",
                        todo_id=1,
                        due="2026-09-01",
                        stima_pomo=2,
                        planned_for=TODAY,
                    )
                ]
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                _why_block_labels(
                    app.screen, T("why_scheduled"), T("why_story_sched_overdue")
                )

        return inner()

    run(t())


def test_why_nessuna_riga_bandiera_in_mezzo_tagliato(tmp_files):
    """Idem sul lato cut, dove il recap capacita' era la riga eliminata."""

    def t():
        async def inner():
            app = make_app([make_todo("Z", todo_id=9, stima_pomo=9)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0], hours=1.0)
                _why_block_labels(
                    app.screen, T("why_not_scheduled"), T("why_story_cut")
                )

        return inner()

    run(t())


def test_why_scheduled_con_evidence_e_motivo(tmp_files):
    def t():
        async def inner():
            app = make_app(
                [
                    make_todo(
                        "A",
                        todo_id=1,
                        due="2026-09-01",
                        stima_pomo=2,
                        planned_for=TODAY,
                    )
                ]
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                assert T("why_scheduled") in txt
                assert T("why_story_sched_overdue") in txt
                assert T("why_sec_details") in txt
                assert "2026-09-01" in txt  # evidence due reale
                assert T("plan_overdue") in txt  # motivo principale reale
                # nessuna riga-flag duplicata: la story le sintetizza
                # (invariante strutturale in test_why_nessuna_riga_bandiera_in_mezzo)

        return inner()

    run(t())


def test_why_not_scheduled_story_neutra(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo(f"T{i}", todo_id=i) for i in range(1, 8)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[4], hours=1.0)
                txt = screen_texts(app.screen)
                assert T("why_not_scheduled") in txt
                assert T("plan_cut") in txt
                assert T("why_story_cut") in txt  # wording neutro, mai capacita'
                assert T("why_sec_details") in txt

        return inner()

    run(t())


def test_why_deferred_con_rimando(tmp_files):
    def t():
        async def inner():
            app = make_app(
                [make_todo("S", todo_id=1, plan_skip=TODAY), make_todo("A", todo_id=2)]
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                assert T("why_deferred") in txt
                assert T("plan_skipped") in txt
                assert T("why_alt_deferred") in txt

        return inner()

    run(t())


def test_why_non_valutato_per_stato(tmp_files):
    def t():
        async def inner():
            done = make_todo("D", todo_id=1)
            done.done = True
            paused = make_todo("P", todo_id=2)
            paused.paused = True
            app = make_app([done, paused])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                assert T("why_no_decision_done") in screen_texts(app.screen)
                await pilot.press("escape")
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[1])
                assert T("why_no_decision_paused") in screen_texts(app.screen)

        return inner()

    run(t())


def test_coerenza_planner_detail_stessi_input(tmp_files):
    # Stessi (todos, today, hours): Detail mostra la decisione del flusso
    # principale. E' il bug che hours dimenticato introdurrebbe.
    todos = [make_todo(f"T{i}", todo_id=i) for i in range(1, 8)]
    expected = {
        d.todo_id: d.decision
        for d in decide(Planner(todos, today=TODAY, hours=1.0).propose(), todos)
    }
    assert expected[5] == dec.NOT_SCHEDULED

    def t():
        async def inner():
            app = make_app(todos)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[4], hours=1.0)
                txt = screen_texts(app.screen)
                assert T("why_not_scheduled") in txt

        return inner()

    run(t())


def test_legacy_default_senza_contesto(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo("A", todo_id=1)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.push_screen(DetailScreen(app.todos[0], app.todos))
                await pilot.pause()
                await pilot.pause()
                assert type(app.screen).__name__ == "DetailScreen"
                txt = screen_texts(app.screen)
                # Task mai pianificato ma proponibile: la card e' onesta
                # (proposta, non finto "in piano").
                assert T("why_proposed") in txt

        return inner()

    run(t())


def test_esc_e_reasons_vuote_senza_crash(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo("A", todo_id=1, due="2099-01-01")])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                ok = await wait_for(
                    pilot, lambda: T("why_sec_details") in screen_texts(app.screen)
                )
                assert ok
                await pilot.press("escape")
                await pilot.pause()
                assert type(app.screen).__name__ != "DetailScreen"

        return inner()

    run(t())


def test_confidence_solo_con_calibration(tmp_files):
    def t():
        async def inner():
            todos = []
            for i in range(1, 11):
                f = make_todo(f"F{i}", todo_id=100 + i, stima_pomo=2)
                f.done = True
                f.completed_at = "2026-09-12 10:00"
                f.actual_pomo = 4
                todos.append(f)
            todos.append(make_todo("A", todo_id=1, stima_pomo=2, due=TODAY))
            app = make_app(todos)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[-1])
                txt = screen_texts(app.screen)
                # primary = primo motivo (due_today); calibrated resta in
                # reasons e accende la confidence M2 sulla durata
                assert T("plan_due_today") in txt
                assert T("why_confidence", c="MEDIUM") in txt

        return inner()

    run(t())


def test_why_oggi_reale_senza_today_esplicito(tmp_files):
    today = datetime.now().strftime("%Y-%m-%d")
    app = make_app([make_todo("A", todo_id=1, due=today)])
    plan = Planner(app.todos, today=today, hours=6.0).propose()
    assert decide(plan, app.todos)[0].decision == dec.SCHEDULED


def test_why_story_sotto_decisione_prima_evidence(tmp_files):
    # Decisione separata dalla spiegazione: story naturale subito sotto la
    # label, prima delle evidence; motivo principale e confidenza invariati.
    def t():
        async def inner():
            todos = []
            for i in range(1, 11):
                f = make_todo(f"F{i}", todo_id=100 + i, stima_pomo=2)
                f.done = True
                f.completed_at = "2026-09-12 10:00"
                f.actual_pomo = 4
                todos.append(f)
            todos.append(
                make_todo("A", todo_id=1, stima_pomo=2, due=TODAY, planned_for=TODAY)
            )
            app = make_app(todos)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[-1])
                txt = screen_texts(app.screen)
                story = T("why_story_sched_due_today")
                assert story in txt
                assert txt.index(T("why_scheduled")) < txt.index(story)
                assert txt.index(story) < txt.index(
                    T("why_ev_score", s=0, r=0, n=0)[:9]
                )
                assert T("plan_due_today") in txt  # motivo principale invariato
                assert T("why_confidence", c="MEDIUM") in txt  # confidenza invariata

        return inner()

    run(t())


def test_why_story_cut_e_deferred_in_detail(tmp_files):
    def t():
        async def inner():
            app = make_app([make_todo(f"T{i}", todo_id=i) for i in range(1, 8)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[4], hours=1.0)
                txt = screen_texts(app.screen)
                assert T("why_story_cut") in txt
                assert txt.index(T("why_not_scheduled")) < txt.index(T("why_story_cut"))
                await pilot.press("escape")
                await pilot.pause()

        return inner()

    run(t())

    def t2():
        async def inner():
            app = make_app(
                [make_todo("S", todo_id=1, plan_skip=TODAY), make_todo("A", todo_id=2)]
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                assert T("why_story_deferred") in txt
                assert txt.index(T("why_deferred")) < txt.index(T("why_story_deferred"))

        return inner()

    run(t2())


def test_why_proposed_con_planned_for_stale(tmp_files):
    # Task pianificato IERI e mai confermato oggi: la card non deve dire
    # "Nel piano di oggi" (il bug segnalato), ma proposta onesta con
    # reasons/evidence/motivo invariati.
    def t():
        async def inner():
            stale = "2026-09-09"
            app = make_app(
                [make_todo("V", todo_id=1, due=TODAY, stima_pomo=2, planned_for=stale)]
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                assert T("why_proposed") in txt
                assert T("why_story_prop_due_today") in txt
                assert T("why_scheduled") not in txt
                assert T("why_story_sched_due_today") not in txt
                assert T("plan_due_today") in txt  # motivo principale invariato
                assert TODAY in txt  # evidence invariata

        return inner()

    run(t())


def test_why_proposed_mai_pianificato_vs_scheduled_in_piano(tmp_files):
    def t():
        async def inner():
            app = make_app(
                [
                    make_todo("N", todo_id=1, due=TODAY),
                    make_todo("P", todo_id=2, due=TODAY, planned_for=TODAY),
                ]
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                assert T("why_proposed") in txt
                assert T("why_scheduled") not in txt
                await pilot.press("escape")
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[1])
                txt2 = screen_texts(app.screen)
                assert T("why_scheduled") in txt2
                assert T("why_proposed") not in txt2

        return inner()

    run(t())


def test_why_story_va_a_capo_senza_clip(tmp_files):
    # Le Label del Detail riempiono la cornice (width 1fr): le story lunghe
    # vanno a capo invece di sbordare tagliate al bordo (bug: `width: auto`,
    # che e' il default proprio di Label -> riga singola da 90 col in box
    # da 60).

    async def check(size):
        app = make_app(
            [make_todo("P", todo_id=1, due=TODAY, stima_pomo=2, planned_for=TODAY)]
        )
        async with app.run_test(size=size) as pilot:
            await pilot.pause()
            await _open_detail(pilot, app, app.todos[0])
            box_w = app.screen.query_one("#detail-box").region.width
            story = None
            for w, text in zip(app.screen.query(Label), label_texts(app.screen)):
                assert w.region.width <= box_w, (size, text[:50])
                if T("why_story_sched_due_today") in text:
                    story = w
            assert story is not None
            assert story.region.height >= 2, (size, story.region)

    def t():
        async def inner():
            await check((120, 40))
            await check((70, 20))

        return inner()

    run(t())


def test_why_senza_duplicazioni(tmp_files):
    # Decisione, story, Dettagli e motivo dicono cose diverse: la story
    # compare una sola volta, mai bandiere doppie, mai heading Perché:.
    def t():
        async def inner():
            app = make_app(
                [
                    make_todo(
                        "A",
                        todo_id=1,
                        due="2026-09-01",
                        stima_pomo=2,
                        planned_for=TODAY,
                    )
                ]
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[0])
                txt = screen_texts(app.screen)
                story = T("why_story_sched_overdue")
                assert txt.count(story) == 1
                assert T("why_sec_details") in txt
                assert T("why_scheduled") in txt
                assert T("why_scheduled") != story

        return inner()

    run(t())


def test_detail_usa_decisions_senza_ricalcolo(tmp_files, monkeypatch):
    # Percorso normale (§12): decisions precalcolate, Planner mai toccato.
    import src.screens.views as views_mod

    calls = []
    orig_plan = views_mod.plan_request

    def counting(request):
        calls.append(1)
        return orig_plan(request)

    # Phase 2 (P2-6): il Detail passa per la facade plan(), non Planner.
    monkeypatch.setattr(views_mod, "plan_request", counting)

    async def inline():
        app = make_app([make_todo("A", todo_id=1, due=TODAY, planned_for=TODAY)])
        precomputed = views_mod.plan_decisions(app.todos, TODAY, 6.0)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # baseline DOPO il mount: l'oggetto del test e' "il Detail non
            # ricalcola", non "l'app non usa mai il planner" (un consumer
            # futuro dell'home romperebbe il test per il motivo sbagliato).
            n_calls = len(calls)
            app.push_screen(
                DetailScreen(
                    app.todos[0],
                    app.todos,
                    today=TODAY,
                    hours=6.0,
                    decisions=precomputed,
                )
            )
            await pilot.pause()
            await pilot.pause()
            assert type(app.screen).__name__ == "DetailScreen"
            assert T("why_scheduled") in screen_texts(app.screen)
            assert len(calls) == n_calls

    run(inline())


def test_why_blocker_capacity_in_coda(tmp_files):
    """P6-4 UIf: voce tagliata con alternatives -> riga Blocco in coda,
    invariante story intatta (una sola riga fra decisione e Dettagli)."""
    from src.screens.views import plan_context

    def t():
        async def inner():
            app = make_app([make_todo(f"T{i}", todo_id=i) for i in range(1, 8)])
            decisions, alternatives = plan_context(app.todos, TODAY, 1.0)
            cut = next(
                t
                for t in app.todos
                if t.id in alternatives and alternatives[t.id].blocked_by == "capacity"
            )
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.push_screen(
                    DetailScreen(
                        cut,
                        app.todos,
                        today=TODAY,
                        hours=1.0,
                        decisions=decisions,
                        alternatives=alternatives,
                    )
                )
                await pilot.pause()
                await pilot.pause()
                txt = screen_texts(app.screen)
                assert T("why_blocked_capacity") in txt
                assert T("why_not_scheduled") in txt
                _why_block_labels(
                    app.screen, T("why_not_scheduled"), T("why_story_cut")
                )

        return inner()

    run(t())


def test_why_blocker_deadline_con_window(tmp_files):
    """P6-4 UIf: scadenza stretta + finestra -> riga Blocco con orario."""
    from src.screens.views import plan_context

    def t():
        async def inner():
            app = make_app(
                [make_todo("A", todo_id=1, due=f"{TODAY} 09:30", stima_pomo=2)]
            )
            window = {"date": TODAY, "start": "09:00", "end": "18:00"}
            decisions, alternatives = plan_context(app.todos, TODAY, 6.0, window)
            assert alternatives[1].blocked_by == "deadline"
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                app.push_screen(
                    DetailScreen(
                        app.todos[0],
                        app.todos,
                        today=TODAY,
                        hours=6.0,
                        decisions=decisions,
                        alternatives=alternatives,
                    )
                )
                await pilot.pause()
                await pilot.pause()
                txt = screen_texts(app.screen)
                assert T("why_blocked_deadline", d="09:30") in txt

        return inner()

    run(t())


def test_why_senza_alternatives_nessuna_riga_blocco(tmp_files):
    """P6-4 UIf fallback: senza alternatives, rendering odierno (nessun Blocco)."""

    def t():
        async def inner():
            app = make_app([make_todo(f"T{i}", todo_id=i) for i in range(1, 8)])
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await _open_detail(pilot, app, app.todos[2], hours=1.0)
                assert "Blocco" not in screen_texts(app.screen)

        return inner()

    run(t())
