"""Invarianti di merge_todo_dicts (P1 §10): documentano la semantica reale.

Non rendono il merge "piu' intelligente": fissano il comportamento
esistente di src/storage.py cosi' un refactor non puo' cambiarlo in silenzio.
"""

import carpediem.storage as m


def _d(i, **kw):
    d = {"id": i, "title": f"T{i}"}
    d.update(kw)
    return d


def _by_id(merged):
    return {d["id"]: d for d in merged if isinstance(d.get("id"), int)}


def test_aggiunte_da_entrambi_sopravvivono():
    merged = m.merge_todo_dicts([], [_d(1)], [_d(2)])
    assert set(_by_id(merged)) == {1, 2}


def test_modifica_da_un_solo_lato_vince():
    base = [_d(1, title="base")]
    disk = [_d(1, title="base")]
    ours = [_d(1, title="nostro")]
    assert _by_id(m.merge_todo_dicts(base, disk, ours))[1]["title"] == "nostro"
    # speculare: modifica solo su disco
    assert (
        _by_id(m.merge_todo_dicts(base, [_d(1, title="disco")], [_d(1, title="base")]))[
            1
        ]["title"]
        == "disco"
    )


def test_modifica_da_entrambi_vince_chi_salva():
    base = [_d(1, title="base")]
    merged = m.merge_todo_dicts(base, [_d(1, title="disco")], [_d(1, title="nostro")])
    assert _by_id(merged)[1]["title"] == "nostro"


def test_cancellato_vs_modificato_vince_la_modifica():
    base = [_d(1, title="base")]
    # cancellato da noi, modificato da loro -> resta la modifica
    assert (
        _by_id(m.merge_todo_dicts(base, [_d(1, title="disco")], []))[1]["title"]
        == "disco"
    )
    # cancellato da loro, modificato da noi -> resta la modifica
    assert (
        _by_id(m.merge_todo_dicts(base, [], [_d(1, title="nostro")]))[1]["title"]
        == "nostro"
    )


def test_cancellato_con_altro_intonso_resta_cancellato():
    base = [_d(1, title="base")]
    assert _by_id(m.merge_todo_dicts(base, [], [_d(1, title="base")])) == {}
    assert _by_id(m.merge_todo_dicts(base, [_d(1, title="base")], [])) == {}


def test_stesso_input_stesse_modifiche_output_deterministico():
    base = [_d(1, title="b"), _d(2, title="b2")]
    disk = [_d(1, title="d"), _d(3, title="n3")]
    ours = [_d(1, title="o"), _d(2, title="b2"), _d(4, title="n4")]
    first = m.merge_todo_dicts(base, disk, ours)
    second = m.merge_todo_dicts(base, disk, ours)
    assert first == second


def test_input_non_mutati():
    import copy

    base, disk, ours = [_d(1, title="b")], [_d(1, title="d")], [_d(1, title="o")]
    snapshots = (copy.deepcopy(base), copy.deepcopy(disk), copy.deepcopy(ours))
    m.merge_todo_dicts(base, disk, ours)
    assert (base, disk, ours) == snapshots
