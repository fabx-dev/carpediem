"""Framework riutilizzabile di UI regression per la TUI CarpeDiem.

Non contiene test: fornisce il tipo ``Scenario`` (registry dichiarativo),
audit generici di layout (esistenza, collasso, viewport, scroll, dimensioni
minime per tipo di widget) e il runner con pilot. Il registry delle screen
vive in ``tests/test_ui_regression.py``.

Principi:
- niente coordinate pixel, screenshot rigidi o dettagli CSS: solo regole
  qualitative stabili alle normali modifiche UI;
- testo critico (titoli, bottoni, errori) verificato sul RENDER effettivo
  (export SVG): intercetta troncamenti reali, non di contenuto;
- un elemento sotto un contenitore scrollabile puo' stare fuori viewport
  (scroll intenzionale); un elemento critico fuori viewport e' un problema;
- i problemi scoperti NON si correggono qui: si documentano nel registry
  (campo ``notes``) o nel report della sessione.
"""

import html
import inspect
import re
from dataclasses import dataclass, field

from textual.containers import ScrollableContainer
from textual.scroll_view import ScrollView

# Quattro livelli: desktop / standard / compatto / piccolo.
SIZES = ((120, 40), (100, 30), (80, 24), (70, 20))

# Widget interattivi sottoposti ad audit generico.
INTERACTIVE = (
    "Input, Select, Button, Checkbox, RadioButton, TextArea, Switch, "
    "SelectionList, ListView, DataTable"
)

# Dimensioni minime ragionevoli PER TIPO (non obbliga tutte le screen alla
# stessa misura): un Input sotto i 2 col e' inutilizzabile, un Button collassato
# a 0 e' un bug. Oltre questi, i vincoli piu' severi si dichiarano per-widget
# tramite Scenario.min_sizes.
MIN_SIZE = {
    "Input": (2, 1),
    "TextArea": (4, 1),
    "Select": (2, 1),
}


@dataclass
class Scenario:
    """Uno scenario di UI regression per una screen/dialog.

    - ``open``: come aprire la screen (async o sync, firma ``(app, pilot)``);
      di solito e' una action dell'app o ``app.push_screen(X(...))``.
    - ``screen``: nome classe attesa come schermata attiva ("" = nessun check).
    - ``critical``: id di widget critici (esistono, non collassati, nel viewport).
    - ``critical_texts``: stringhe che devono apparire INTERE nel render
      (intercetta troncamento tipo "Salva..." su bottoni/titoli/label).
    - ``expect_texts``: dati di dominio che devono essere rappresentati nella
      UI (contenuto dei widget O render).
    - ``post_texts``: come expect_texts ma verificati DOPO l'interazione.
    - ``top_containers``: id di scroll che devono aprire a inizio (scroll_y 0).
    - ``interact``: interazione minima opzionale (firma ``(pilot, app, screen)``).
    - ``min_sizes``: regole minime esplicite per widget critico ``{id: (w, h)}``.
    - ``lenient``: id esenti dalle minime generiche (motivazione in ``notes``).
    - ``no_close``: True se la chiusura con escape NON fa parte del contratto.
    - ``skip_sizes``: {(w, h): motivo} per escludere una taglia motivata.
    - ``notes``: motivazioni/limiti noti (anche problemi UI scoperti, non fixati).
    """

    name: str
    open: object
    screen: str = ""
    todos: object | None = None  # factory dei dati di dominio (lista TodoItem)
    setup: object | None = None  # setup opzionale sull'app prima dell'apertura
    critical: tuple[str, ...] = ()
    critical_texts: tuple[str, ...] = ()
    expect_texts: tuple[str, ...] = ()
    post_texts: tuple[str, ...] = ()
    top_containers: tuple[str, ...] = ()
    interact: object | None = None
    min_sizes: dict[str, tuple[int, int]] = field(default_factory=dict)
    lenient: tuple[str, ...] = ()
    no_close: bool = False
    skip_sizes: dict[tuple[int, int], str] = field(default_factory=dict)
    notes: str = ""


def rendered_text(app) -> tuple[str, str]:
    """Testo realmente renderizzato (export SVG): (con-spazi, senza-spazi).

    Il secondo variante gestisce run di stile che spezzano una stringa:
    per il containment check basta una delle due forme.
    """
    svg = app.export_screenshot()
    parts = [
        html.unescape(m) for m in re.findall(r"<text[^>]*>(.*?)</text>", svg, re.S)
    ]
    with_spaces = " ".join(p.replace("\xa0", " ") for p in parts)
    return with_spaces, with_spaces.replace(" ", "")


def screen_content_text(screen) -> str:
    """Contenuto dichiarato di Static/Label/Button (senza passare dal render).

    Le label dei Button sono contenuto dichiarato (presenza del dato), come
    Static/Label: la leggibilita' effettiva (troncamenti) resta verificata
    sul render via critical_texts."""
    from textual.widgets import Button

    out = []
    for w in list(screen.query("Static")) + list(screen.query("Label")):
        content = getattr(w, "content", None)
        if content is None:
            content = getattr(w, "renderable", "")
        out.append(str(content))
    for w in screen.query(Button):
        try:
            out.append(str(w.label))
        except Exception:
            pass
    return " ".join(out)


def _in_scrollable(widget, screen) -> bool:
    # ScrollableContainer copre Vertical/HorizontalScroll (in Textual 3.x NON
    # e' un ScrollView); is_scrollable copre i widget a scroll nativo montati.
    node = widget.parent
    while node is not None and node is not screen:
        if isinstance(node, (ScrollView, ScrollableContainer)) or bool(
            getattr(node, "is_scrollable", False)
        ):
            return True
        node = node.parent
    return False


def _visible_area(region, width: int, height: int) -> int:
    x1 = max(region.x, 0)
    y1 = max(region.y, 0)
    x2 = min(region.x + region.width, width)
    y2 = min(region.y + region.height, height)
    return max(0, x2 - x1) * max(0, y2 - y1)


def audit_screen(screen, size: tuple[int, int], scenario: Scenario) -> list[str]:
    """Audit generico di layout; restituisce l'elenco dei problemi trovati."""
    problems: list[str] = []
    width, height = size

    for cid in scenario.critical:
        if not screen.query(f"#{cid}"):
            problems.append(f"widget critico #{cid} assente")

    for widget in screen.query(INTERACTIVE):
        wid = widget.id or "<senza-id>"
        cls = type(widget).__name__
        tag = f"{cls}#{wid}"
        region = widget.region
        if region.width <= 0 or region.height <= 0:
            problems.append(f"{tag} collassato (region={region}) a {size}")
            continue
        if wid not in scenario.lenient:
            mw, mh = MIN_SIZE.get(cls, (1, 1))
            if region.width < mw or region.height < mh:
                problems.append(
                    f"{tag} sotto il minimo ({region.width}x{region.height} < {mw}x{mh}) a {size}"
                )
        area = _visible_area(region, width, height)
        if area <= 0:
            if wid in scenario.critical:
                problems.append(
                    f"{tag} critico fuori viewport (region={region}) a {size}"
                )
            elif not _in_scrollable(widget, screen):
                problems.append(
                    f"{tag} fuori viewport senza contenitore scrollabile "
                    f"(region={region}) a {size}"
                )
        if wid in scenario.min_sizes:
            mw, mh = scenario.min_sizes[wid]
            if region.width < mw or region.height < mh:
                problems.append(
                    f"{tag} sotto il minimo dichiarato "
                    f"({region.width}x{region.height} < {mw}x{mh}) a {size}"
                )
    return problems


def _check_texts(app, screen, scenario: Scenario) -> list[str]:
    """Testo critico = leggibilita' nel render; dati attesi = contenuto/render."""
    problems: list[str] = []
    if scenario.critical_texts or scenario.expect_texts:
        rendered, rendered_compact = rendered_text(app)
        for wanted in scenario.critical_texts:
            norm = " ".join(wanted.split())
            if norm not in rendered and norm.replace(" ", "") not in rendered_compact:
                problems.append(
                    f"testo critico non leggibile nel render (troncato?): {wanted!r}"
                )
        content = screen_content_text(screen)
        for wanted in scenario.expect_texts:
            norm = " ".join(wanted.split())
            if (
                norm not in content
                and norm not in rendered
                and norm.replace(" ", "") not in rendered_compact
            ):
                problems.append(
                    f"dato di dominio non rappresentato nella UI: {wanted!r}"
                )
    return problems


async def run_scenario(app, scenario: Scenario, size: tuple[int, int]) -> list[str]:
    """Apre lo scenario, esegue gli audit, interagisce, chiude con escape."""
    problems: list[str] = []
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        result = scenario.open(app, pilot)
        if inspect.isawaitable(result):
            await result
        await pilot.pause()
        await pilot.pause()

        if scenario.screen and type(app.screen).__name__ != scenario.screen:
            problems.append(
                f"schermata attesa {scenario.screen}, attiva {type(app.screen).__name__}"
            )
            return problems

        problems += audit_screen(app.screen, size, scenario)

        for cid in scenario.top_containers:
            try:
                container = app.screen.query_one(f"#{cid}")
            except Exception:
                problems.append(f"container #{cid} (top_containers) assente")
                continue
            if getattr(container, "scroll_y", 0) > 0.01:
                problems.append(
                    f"#{cid} apre gia' scrollato verso il fondo "
                    f"(scroll_y={container.scroll_y}) a {size}"
                )

        problems += _check_texts(app, app.screen, scenario)

        if scenario.interact is not None:
            await scenario.interact(pilot, app, app.screen)
            await pilot.pause()
            await pilot.pause()
            problems += [
                f"[dopo-interazione] {p}"
                for p in audit_screen(app.screen, size, scenario)
            ]
            if scenario.post_texts:
                rendered, rendered_compact = rendered_text(app)
                content = screen_content_text(app.screen)
                for wanted in scenario.post_texts:
                    norm = " ".join(wanted.split())
                    if (
                        norm not in content
                        and norm not in rendered
                        and norm.replace(" ", "") not in rendered_compact
                    ):
                        problems.append(
                            f"[dopo-interazione] dato non rappresentato nella UI: {wanted!r}"
                        )

        if not scenario.no_close:
            # Esc a stadi (es. menu: filtro -> sottomenu -> chiusura): fino a
            # 3 pressioni, poi la schermata deve essere andata. Pressioni in
            # eccesso a schermata chiusa sono no-op (Esc sulla home pulisce
            # solo la ricerca attiva).
            for _ in range(3):
                if type(app.screen).__name__ != scenario.screen:
                    break
                await pilot.press("escape")
                await pilot.pause()
                await pilot.pause()
            if type(app.screen).__name__ == scenario.screen:
                problems.append("escape non chiude la schermata")
    return problems
