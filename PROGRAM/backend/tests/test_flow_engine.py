from app.flow_engine import _next_node_id, validate_graph


def test_next_node_default():
    g = {"edges": [{"source": "a", "target": "b"}]}
    assert _next_node_id(g, "a") == "b"
    assert _next_node_id(g, "missing") is None


def test_next_node_condition_branches():
    g = {"edges": [
        {"source": "c", "sourceHandle": "true", "target": "yes"},
        {"source": "c", "sourceHandle": "false", "target": "no"},
    ]}
    assert _next_node_id(g, "c", handle="true") == "yes"
    assert _next_node_id(g, "c", handle="false") == "no"


def test_next_node_condition_missing_handle_falls_back_to_default():
    g = {"edges": [
        {"source": "c", "sourceHandle": "true", "target": "yes"},
        {"source": "c", "target": "default"},
    ]}
    # false-ветки нет — fallback на edge без handle
    assert _next_node_id(g, "c", handle="false") == "default"


def test_validate_graph_ok():
    g = {
        "nodes": [
            {"id": "a", "data": {"kind": "start"}},
            {"id": "b", "data": {"kind": "message", "text": "hi"}},
            {"id": "c", "data": {"kind": "end"}},
        ],
        "edges": [
            {"source": "a", "target": "b"},
            {"source": "b", "target": "c"},
        ],
    }
    assert validate_graph(g) == []


def test_validate_graph_unreachable():
    g = {
        "nodes": [
            {"id": "a", "data": {"kind": "start"}},
            {"id": "b", "data": {"kind": "message"}},
            {"id": "lonely", "data": {"kind": "message"}},
        ],
        "edges": [{"source": "a", "target": "b"}],
    }
    errs = validate_graph(g)
    assert any("unreachable" in e for e in errs)


def test_validate_graph_unknown_kind():
    g = {
        "nodes": [{"id": "a", "data": {"kind": "nonsense"}}],
        "edges": [],
    }
    errs = validate_graph(g)
    assert any("unknown kind" in e for e in errs)
