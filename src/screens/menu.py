"""Menu per funzioni (m) a due colonne. Dipendono solo da models/storage/lang/nlparse/plan/domain (+ _shared). Mai app."""

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Label,
    Static,
)

from src.lang import (
    T,
)
from src.screens._shared import _escape_markup


class MenuRow(Label):
    """Riga selezionabile del menu: focus + click, senza debounce dei Button."""

    can_focus = True

    async def on_click(self, event) -> None:
        # Gestito qui (la riga conosce il proprio id): alle coordinate
        # dell'evento in bolla non ci si puo' affidare (offset consumati).
        try:
            event.stop()
        except Exception:
            pass
        try:
            cb = getattr(self.screen, "menu_row_clicked", None)
            if callable(cb):
                cb(self.id or "")
        except Exception:
            pass


class MenuScreen(ModalScreen[str | None]):
    """Menu per funzioni: voci a sinistra, sottomenu a destra.

    Riceve categorie gia' risolte nella lingua corrente:
    [(titolo_cat, aiuto_cat, [(titolo, aiuto, action, shortcut|None), ...]), ...].
    La colonna di sinistra mostra solo i titoli delle categorie; click/Enter su
    una voce apre il sottomenu nel pannello di destra, un nuovo click sulla
    stessa voce lo chiude. Tutto allineato a sinistra, righe compatte
    (titolo + aiuto grigio sotto). Su/giu scorrono le voci (con anteprima) e le
    righe del sottomenu, destra/Enter entra ed esegue, sinistra torna alle voci,
    1-4 saltano alle categorie, la digitazione filtra le voci, esc chiude
    (prima svuota il filtro, poi il sottomenu, poi il menu).
    Il dismiss ritorna il nome dell'action scelta (es. "action_open_settings")
    oppure None se chiuso senza scelta. Non importa mai app/commands.

    Nota: le righe sono MenuRow (Label), non Button — cosi' il Click del mouse
    (gestito in on_click) e l'Enter da tastiera (binding activate) restano
    distinguibili (Button.Pressed li confonde) e non c'e' debounce -active.
    """

    CSS = """
    #menu-box {
        width: 80;
        max-width: 94%;
        height: 100%;
        max-height: 100%;
        dock: right;
    }
    #menu-title {
        text-align: left;
    }
    #menu-count {
        height: auto;
        color: $text-muted;
        text-align: left;
        margin-bottom: 1;
    }
    #menu-count.hidden {
        display: none;
    }
    #menu-main {
        width: 100%;
        height: 1fr;
        margin-bottom: 1;
    }
    #menu-bar {
        width: 24;
        height: 100%;
        margin-top: 1;
        margin-right: 1;
    }
    #menu-bar MenuRow {
        width: 100%;
        height: 1;
        margin-bottom: 1;
    }
    #menu-bar MenuRow.active {
        text-style: bold;
        background: $primary-darken-2;
    }
    #menu-bar MenuRow:focus, #menu-drop MenuRow:focus {
        background: $primary-darken-1;
        text-style: bold;
    }
    #menu-bar MenuRow:hover, #menu-drop MenuRow:hover {
        text-style: underline;
    }
    #menu-drop {
        width: 1fr;
        height: 100%;
        border: solid $primary;
        background: $surface;
    }
    #menu-drop .hidden {
        display: none;
    }
    #menu-drop MenuRow {
        width: 100%;
        height: 2;
        margin-bottom: 0;
    }
    #menu-empty {
        height: auto;
        padding: 1 2;
        color: $text-muted;
    }
    #menu-hint {
        height: auto;
        color: $text-muted;
        text-align: left;
        margin-bottom: 1;
    }
    """

    BINDINGS = [
        Binding("left", "cursor_left", "Indietro", show=False),
        Binding("right", "cursor_right", "Avanti", show=False),
        Binding("up", "cursor_up", "Su", show=False),
        Binding("down", "cursor_down", "Giu", show=False),
        Binding("enter", "activate", "Apri/Esegui", show=False),
        Binding("space", "activate", "Apri/Esegui", show=False),
        Binding("backspace", "filter_back", "Cancella filtro", show=False),
        Binding("escape", "close_or_shrink", "Chiudi"),
    ]

    def __init__(
        self,
        categories: list[tuple[str, str, list[tuple[str, str, str, str | None]]]],
    ) -> None:
        super().__init__()
        self.categories = categories
        self._open_idx: int | None = None
        self._filter: str = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="menu-box"):
            yield Label(T("menu_title"), id="menu-title")
            yield Label(T("menu_hint"), id="menu-hint")
            yield Static("", id="menu-count", classes="hidden")
            with Horizontal(id="menu-main"):
                with Vertical(id="menu-bar"):
                    for i in range(len(self.categories)):
                        yield MenuRow("", id=f"menu-cat-{i}")
                with VerticalScroll(id="menu-drop", can_focus=False):
                    yield Static(T("menu_pick"), id="menu-empty")
                    for gi, (_ct, _ch, gitems) in enumerate(self.categories):
                        with Vertical(
                            id=f"menu-drop-{gi}", classes="menu-drop-group hidden"
                        ):
                            for gj in range(len(gitems)):
                                yield MenuRow("", id=f"menu-item-{gi}-{gj}")
            yield Button(T("ui_close_esc"), id="menu-close", variant="default")

    def on_mount(self) -> None:
        self._refresh_texts()
        self._open(0, focus_item=None)
        self._focus_cat(0)

    # -- helpers ---------------------------------------------------------
    def _cat_rows(self) -> list[MenuRow]:
        return [
            w
            for w in self.query("#menu-bar MenuRow")
            if isinstance(w, MenuRow) and (w.id or "").startswith("menu-cat-")
        ]

    def _group_visible(self, gi: int) -> bool:
        try:
            return not self.query_one(f"#menu-drop-{gi}").has_class("hidden")
        except Exception:
            return False

    def _item_rows(self) -> list[MenuRow]:
        out: list[MenuRow] = []
        for gi in range(len(self.categories)):
            if not self._group_visible(gi):
                continue
            try:
                out.extend(
                    w
                    for w in self.query(f"#menu-drop-{gi} MenuRow")
                    if isinstance(w, MenuRow) and not w.has_class("hidden")
                )
            except Exception:
                pass
        return out

    def _parse_item_id(self, fid: str) -> tuple[int, int] | None:
        parts = (fid or "").split("-")
        if len(parts) == 4 and parts[0] == "menu" and parts[1] == "item":
            try:
                return int(parts[2]), int(parts[3])
            except ValueError:
                return None
        return None

    def _focused_cat(self) -> int | None:
        fid = getattr(self.focused, "id", "") or ""
        if fid.startswith("menu-cat-"):
            try:
                return int(fid[len("menu-cat-") :])
            except ValueError:
                return None
        return None

    def _focused_item(self) -> tuple[int, int] | None:
        parsed = self._parse_item_id(getattr(self.focused, "id", "") or "")
        if parsed is None or not self._group_visible(parsed[0]):
            return None
        return parsed

    def _focus_cat(self, i: int) -> None:
        try:
            self.query_one(f"#menu-cat-{i}", MenuRow).focus()
        except Exception:
            pass

    def _focus_item(self, i: int, j: int) -> None:
        try:
            self.query_one(f"#menu-item-{i}-{j}", MenuRow).focus()
        except Exception:
            pass

    def _set_active(self, i: int | None) -> None:
        for k, w in enumerate(self._cat_rows()):
            try:
                w.set_class(k == i, "active")
            except Exception:
                pass
        self._refresh_bar()

    def _refresh_bar(self) -> None:
        for i in range(len(self.categories)):
            try:
                self.query_one(f"#menu-cat-{i}", MenuRow).update(self._cat_label(i))
            except Exception:
                pass

    # -- testi -----------------------------------------------------------
    def _cat_label(self, i: int) -> str:
        ct = self.categories[i][0]
        n = len(self.categories[i][2])
        mark = "›" if self._open_idx == i else " "
        return f"{mark} {ct} ({n})"

    def _item_text(self, t: str, h: str, sc: str | None) -> Text:
        title = f"{t} ({sc})" if sc else t
        return Text.from_markup(f"{title}\n[dim]{h}[/]")

    def _refresh_texts(self) -> None:
        for i in range(len(self.categories)):
            try:
                self.query_one(f"#menu-cat-{i}", MenuRow).update(self._cat_label(i))
            except Exception:
                pass
            for j, (t, h, _action, sc) in enumerate(self.categories[i][2]):
                try:
                    self.query_one(f"#menu-item-{i}-{j}", MenuRow).update(
                        self._item_text(t, h, sc)
                    )
                except Exception:
                    pass

    # -- filtro ----------------------------------------------------------
    def _match(self, gi: int, gj: int) -> bool:
        q = self._filter.strip().lower()
        if not q:
            return True
        try:
            t, h, _action, sc = self.categories[gi][2][gj]
        except IndexError:
            return False
        return q in f"{t} {h} {sc or ''}".lower()

    def _apply_filter(self) -> None:
        n = 0
        for gi in range(len(self.categories)):
            shown = 0
            for gj in range(len(self.categories[gi][2])):
                try:
                    w = self.query_one(f"#menu-item-{gi}-{gj}", MenuRow)
                except Exception:
                    continue
                if self._filter.strip():
                    ok = self._match(gi, gj)
                    try:
                        w.set_class(not ok, "hidden")
                    except Exception:
                        pass
                    if ok:
                        shown += 1
                else:
                    try:
                        w.remove_class("hidden")
                    except Exception:
                        pass
            try:
                grp = self.query_one(f"#menu-drop-{gi}")
                if self._filter.strip():
                    grp.set_class(shown == 0, "hidden")
                else:
                    grp.set_class(gi != self._open_idx, "hidden")
            except Exception:
                pass
            n += shown
        try:
            count = self.query_one("#menu-count", Static)
            empty = self.query_one("#menu-empty", Static)
            if self._filter.strip():
                count.update(T("menu_filter", q=_escape_markup(self._filter), n=n))
                count.remove_class("hidden")
                if n == 0:
                    empty.update(T("menu_no_match", q=_escape_markup(self._filter)))
                    empty.remove_class("hidden")
                else:
                    empty.add_class("hidden")
            else:
                count.update("")
                count.add_class("hidden")
                if self._open_idx is None:
                    empty.update(T("menu_pick"))
                    empty.remove_class("hidden")
                else:
                    empty.add_class("hidden")
        except Exception:
            pass

    # -- apertura/chiusura sottomenu --------------------------------------
    def _open(self, i: int, focus_item: int | None = 0) -> None:
        if not 0 <= i < len(self.categories):
            return
        self._open_idx = i
        self._apply_filter()
        self._set_active(i)
        if focus_item is None:
            return

        def _defer() -> None:
            if self._open_idx != i:
                return
            self._focus_item(i, focus_item)

        try:
            self.call_after_refresh(_defer)
        except Exception:
            _defer()

    def _close_drop(self, focus_cat: bool = True) -> None:
        idx = self._open_idx
        self._open_idx = None
        self._apply_filter()
        self._set_active(None)
        if focus_cat:
            self._focus_cat(idx if idx is not None else 0)

    def _run_item(self, gi: int, gj: int) -> None:
        try:
            action = self.categories[gi][2][gj][2]
        except IndexError:
            return
        self.dismiss(action)

    # -- eventi ----------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if (event.button.id or "") == "menu-close":
            self.dismiss(None)

    def menu_row_clicked(self, bid: str) -> None:
        if bid.startswith("menu-cat-"):
            try:
                idx = int(bid[len("menu-cat-") :])
            except ValueError:
                return
            if self._open_idx == idx:
                self._close_drop()
            else:
                self._open(idx)
        elif bid.startswith("menu-item-"):
            parsed = self._parse_item_id(bid)
            if parsed is None or not self._group_visible(parsed[0]):
                return
            self._run_item(*parsed)

    def on_key(self, event) -> None:
        ch = getattr(event, "character", None)
        if not ch or len(ch) != 1 or not ch.isprintable() or ch == " ":
            return
        if getattr(event, "ctrl", False) or getattr(event, "meta", False):
            return
        # Consuma il tasto qui: i binding globali dell'app (b, c, k, ...)
        # non devono scattare mentre si filtra nel menu.
        try:
            event.prevent_default()
            event.stop()
        except Exception:
            pass
        if ch in ("1", "2", "3", "4") and not self._filter.strip():
            idx = int(ch) - 1
            if idx < len(self.categories):
                self._open(idx)
            return
        self._filter += ch
        self._apply_filter()

    # -- tastiera: frecce, invio, esc -------------------------------------
    def action_activate(self) -> None:
        fid = getattr(self.focused, "id", "") or ""
        if fid == "menu-close":
            return
        cat = self._focused_cat()
        if cat is not None:
            self._open(cat, focus_item=0)
            return
        item = self._focused_item()
        if item is not None:
            self._run_item(*item)

    def action_cursor_left(self) -> None:
        focused = self._focused_item()
        if focused is not None:
            self._focus_cat(focused[0])

    def action_cursor_right(self) -> None:
        cat = self._focused_cat()
        if cat is not None:
            self._open(cat, focus_item=0)
        elif self._open_idx is None and not self._filter.strip():
            self._open(0, focus_item=0)

    def action_cursor_down(self) -> None:
        focused = self._focused_item()
        if focused is not None:
            rows = self._item_rows()
            ids = [w.id for w in rows]
            try:
                pos = ids.index(f"menu-item-{focused[0]}-{focused[1]}")
            except ValueError:
                pos = -1
            if rows:
                nxt_row = rows[(pos + 1) % len(rows)]
                try:
                    nxt_row.focus()
                except Exception:
                    pass
            return
        cat = self._focused_cat()
        if cat is None:
            cat = self._open_idx if self._open_idx is not None else 0
        if self._filter.strip():
            rows = self._item_rows()
            if rows:
                try:
                    rows[0].focus()
                except Exception:
                    pass
            return
        nxt = (cat + 1) % len(self.categories)
        self._open(nxt, focus_item=None)
        self._focus_cat(nxt)

    def action_cursor_up(self) -> None:
        focused = self._focused_item()
        if focused is not None:
            if self._filter.strip():
                rows = self._item_rows()
                ids = [w.id for w in rows]
                try:
                    pos = ids.index(f"menu-item-{focused[0]}-{focused[1]}")
                except ValueError:
                    pos = 0
                if rows:
                    try:
                        rows[(pos - 1) % len(rows)].focus()
                    except Exception:
                        pass
                return
            if focused[1] <= 0:
                self._focus_cat(focused[0])
            else:
                self._focus_item(focused[0], focused[1] - 1)
            return
        cat = self._focused_cat()
        if cat is None:
            cat = self._open_idx if self._open_idx is not None else 0
        if self._filter.strip():
            rows = self._item_rows()
            if rows:
                try:
                    rows[-1].focus()
                except Exception:
                    pass
            return
        nxt = (cat - 1) % len(self.categories)
        self._open(nxt, focus_item=None)
        self._focus_cat(nxt)

    def action_filter_back(self) -> None:
        if self._filter:
            self._filter = self._filter[:-1]
            self._apply_filter()

    def action_close_or_shrink(self) -> None:
        if self._filter.strip():
            self._filter = ""
            self._apply_filter()
            return
        if self._open_idx is not None:
            self._close_drop()
        else:
            self.dismiss(None)
