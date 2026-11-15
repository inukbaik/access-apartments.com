"""Schema and validation tests with made-up data (no network, temp cache dirs).
Run from the repo root: .venv/bin/python finder/test_schemas.py"""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from finder import llm, matterport, vexcel  # noqa: E402
from finder.llm import LLMError, OpenAICompatBackend  # noqa: E402
from finder.matterport import FetchError, fetch_model  # noqa: E402
from finder.schemas import DataError, EvidenceModel, ScreenModel, validate  # noqa: E402

MODEL: dict[str, Any] = {
    "id": "abc", "name": "Test flat",
    "rooms": [{"id": "r0", "classifications": [{"label": "Hallway", "confidence": 0.9}],
               "dimensions": {"areaFloor": 6.0, "width": 1.2, "depth": 5.0, "height": 2.4},
               "boundary": {"edges": [{"id": "e0"}]}}],
    "floors": [{"id": "f0", "label": "Floor 1",
                "edges": [{"id": "e0", "type": "wall", "thickness": 0.1,
                           "openings": [{"type": "doorway", "label": "", "width": 0.9, "height": 2.0,
                                         "lowerElevation": 0}]}]}],
}


def fails(model, data, what="X"):
    try:
        validate(model, data, what)
    except DataError as e:
        return str(e)
    raise AssertionError("expected DataError")


# --- Matterport screening schema
before = copy.deepcopy(MODEL)
validate(ScreenModel, MODEL, "Matterport model abc")  # returns nothing, raises on bad data
assert MODEL == before  # validate never changes the dict

bad = copy.deepcopy(MODEL)
bad["rooms"].append(copy.deepcopy(bad["rooms"][0]))
bad["rooms"][1]["dimensions"]["width"] = "3.2"
msg = fails(ScreenModel, bad, "Matterport model abc")
assert msg == "Matterport model abc: rooms.1.dimensions.width: expected a number, got str", msg

bad = copy.deepcopy(MODEL)
bad["rooms"][0]["dimensions"]["depth"] = True
assert "rooms.0.dimensions.depth: expected a number, got bool" in fails(ScreenModel, bad)

ok = copy.deepcopy(MODEL)
ok["rooms"][0]["dimensions"]["width"] = 2  # int where a float is expected
ok["floors"][0]["edges"][0]["openings"][0]["width"] = None  # null = no data, not a schema error
ok["unknown_field"] = {"anything": 1}
ok["rooms"][0]["extra"] = "ignored"
validate(ScreenModel, ok, "X")

for v in (float("nan"), float("inf")):
    bad = copy.deepcopy(MODEL)
    bad["rooms"][0]["dimensions"]["width"] = v
    assert "rooms.0.dimensions.width: expected a finite number" in fails(ScreenModel, bad)

# negative values are checks.py's business, not the schema's
neg = copy.deepcopy(MODEL)
neg["rooms"][0]["dimensions"]["width"] = -1.0
validate(ScreenModel, neg, "X")

assert "(top level): expected an object, got list" in fails(ScreenModel, [])
bad = copy.deepcopy(MODEL)
bad["rooms"] = {"not": "a list"}
assert "rooms: expected a list, got dict" in fails(ScreenModel, bad)
# long payloads never end up in the message
many = {"rooms": [{"dimensions": {"width": "x" * 5000}} for _ in range(10)]}
msg = fails(ScreenModel, many)
assert len(msg) < 400 and "xxxx" not in msg and "(+7 more)" in msg, msg

# --- evidence schema
EV: dict[str, Any] = {"id": "abc", "name": "n",
      "floors": [{"id": "f0", "label": "Floor 1", "edges": [
          {"id": "e0", "type": "wall",
           "vertices": [{"position": {"x": 0, "y": 0}}, {"position": {"x": 1.5, "y": 0}}],
           "openings": [{"id": "o0", "type": "doorway", "width": 0.9, "relativeCenter": 0.5}]}]}],
      "panoLocations": [{"id": "p0", "label": "1", "position": {"x": 1, "y": 2, "z": 0},
                         "rotation": {"x": 0, "y": 0, "z": 0, "w": 1}, "anchor": {"floor": {"id": "f0"}},
                         "skybox": {"status": "available", "children": ["u1"]}}]}
validate(EvidenceModel, EV, "X")
bad = copy.deepcopy(EV)
bad["floors"][0]["edges"][0]["vertices"][1]["position"]["x"] = "1.5"
assert "floors.0.edges.0.vertices.1.position.x: expected a number" in fails(EvidenceModel, bad)

# --- Vexcel: garbage gives "unavailable", does not set the down flag, is not cached
class Resp:
    def __init__(self, body: Any, status: int = 200):
        self.body, self.status_code, self.text = body, status, json.dumps(body)[:50]

    def json(self) -> Any:
        return self.body


def run_vexcel(body: Any, cache_dir: str) -> tuple[dict[str, Any], str, int]:
    calls: list[int] = []

    def fake_get(*a: Any, **k: Any) -> Resp:
        calls.append(1)
        return Resp(body)

    real_get, real_key, real_dir = vexcel.requests.get, vexcel._key, vexcel.CACHE_DIR
    setattr(vexcel.requests, "get", fake_get)
    vexcel._key = lambda: "fake-key"
    vexcel.CACHE_DIR = cache_dir
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            res = vexcel.building_height(34.0, -118.0)
    finally:
        setattr(vexcel.requests, "get", real_get)
        vexcel._key, vexcel.CACHE_DIR = real_key, real_dir
    return res, buf.getvalue(), len(calls)


os.environ["VEXCEL_API_KEY"] = "fake-key"
with tempfile.TemporaryDirectory() as tmp:
    for garbage in (["a list"], {"features": "nope"}, {"features": [{"properties": {"metadata.is-ortho-image": "yes"}}]},
                    {"features": [{"properties": {"structures": [{"roof-characteristics.height": "12"}]}}]},
                    {"features": [{"properties": {"structures": [{"roof-characteristics.height": float("nan")}]}}]}):
        vexcel._state["down"] = False
        res, out, n = run_vexcel(garbage, os.path.join(tmp, "v"))
        assert res["status"] == "unavailable" and res["reason"] == "unexpected Vexcel data", res
        assert vexcel._state["down"] is False and n == 1
        assert out.count("\n") == 1 and "Vexcel data" in out, out
        assert not os.path.exists(os.path.join(tmp, "v")) or not os.listdir(os.path.join(tmp, "v"))  # not cached
    # a valid flat-key response still works and is cached
    good = {"features": [{"properties": {
        "metadata.is-ortho-image": True, "metadata.ortho-date-estimate": "2024-01-01T00:00:00Z",
        "metadata.collection": "c", "structures": [
            {"footprint.wkt": "POLYGON((-118.1 33.9,-117.9 33.9,-117.9 34.1,-118.1 34.1,-118.1 33.9))",
             "roof-characteristics.height": 10}]}}]}
    res, out, n = run_vexcel(good, os.path.join(tmp, "v2"))
    assert res["status"] == "ok" and res["height_m"] == 10.0 and len(os.listdir(os.path.join(tmp, "v2"))) == 1, res

    # invalid cached result = cache miss (fetches again), valid cached result = hit
    d = os.path.join(tmp, "v3")
    os.makedirs(d)
    cache_file = os.path.join(d, "34.000000_-118.000000.json")
    with open(cache_file, "w") as f:
        json.dump({"status": "maybe", "height_m": "12"}, f)
    res, out, n = run_vexcel(good, d)
    assert n == 1 and res["status"] == "ok", (n, res)
    res, out, n = run_vexcel(["unused"], d)  # now cached and valid: no network call
    assert n == 0 and res["status"] == "ok", (n, res)
    with open(cache_file, "w") as f:
        f.write("{not json")
    res, out, n = run_vexcel(good, d)
    assert n == 1 and res["status"] == "ok"

# --- fetch_model: malformed cache file raises FetchError
with tempfile.TemporaryDirectory() as tmp:
    real_dir, real_graph = matterport.CACHE_DIR, matterport.graph
    matterport.CACHE_DIR = tmp
    try:
        bad = copy.deepcopy(MODEL)
        bad["rooms"][0]["dimensions"]["width"] = "wide"
        with open(os.path.join(tmp, "sid1.json"), "w") as f:
            json.dump(bad, f)
        try:
            fetch_model("sid1")
            raise AssertionError("expected FetchError")
        except FetchError as e:
            assert "rooms.0.dimensions.width: expected a number, got str" in str(e), e
        with open(os.path.join(tmp, "sid2.json"), "w") as f:
            json.dump(MODEL, f)
        assert fetch_model("sid2") == MODEL  # valid cache: same dict back
        # fresh invalid data: FetchError and nothing written to the cache
        matterport.graph = lambda q, v=None: ({"model": bad}, None)
        try:
            fetch_model("sid3")
            raise AssertionError("expected FetchError")
        except FetchError:
            assert not os.path.exists(os.path.join(tmp, "sid3.json"))
        matterport.graph = lambda q, v=None: (["not", "a", "dict"], None)
        try:
            fetch_model("sid4")
            raise AssertionError("expected FetchError")
        except FetchError as e:
            assert "unexpected data" in str(e)
        matterport.graph = lambda q, v=None: ({"model": MODEL}, None)
        assert fetch_model("sid5") == MODEL and os.path.exists(os.path.join(tmp, "sid5.json"))
    finally:
        matterport.CACHE_DIR, matterport.graph = real_dir, real_graph


# --- LLM
def chat_with(body, status=200):
    real = llm.requests.post
    setattr(llm.requests, "post", lambda *a, **k: Resp(body, status))
    try:
        return OpenAICompatBackend(base_url="http://x/v1", model="m").chat([], [])
    finally:
        setattr(llm.requests, "post", real)


def call(args):
    fn = {"name": "finish"} if args is ... else {"name": "finish", "arguments": args}
    return {"choices": [{"message": {"content": None, "tool_calls": [{"id": "c1", "function": fn}]}}]}


text, calls = chat_with(call({"ids": ["a"]}))  # object
assert calls == [{"id": "c1", "name": "finish", "arguments": '{"ids": ["a"]}'}], calls
text, calls = chat_with(call('{"ids": ["a"]}'))  # string
assert calls[0]["arguments"] == '{"ids": ["a"]}'
text, calls = chat_with(call(None))  # null
assert calls[0]["arguments"] == "{}"
text, calls = chat_with(call(...))  # missing
assert calls[0]["arguments"] == "{}"
text, calls = chat_with({"choices": [{"message": {"content": "<think>x</think>hi"}}]})
assert text == "hi" and calls == []
bodies: list[Any] = [{}, [], {"choices": []}, {"choices": [{}]}, {"choices": [{"message": {"content": 5}}]},
             {"choices": [{"message": {"tool_calls": [{"function": {}}]}}]},
             {"choices": [{"message": {"tool_calls": "x"}}]}]
for body in bodies:
    try:
        chat_with(body)
        raise AssertionError(f"expected LLMError for {body}")
    except LLMError as e:
        assert str(e).startswith("malformed LLM response"), e


def models_with(body):
    real = llm.requests.get
    setattr(llm.requests, "get", lambda *a, **k: type("R", (), {"raise_for_status": lambda s: None, "json": lambda s: body})())
    try:
        OpenAICompatBackend(base_url="http://x/v1", model="m").preflight()
    finally:
        setattr(llm.requests, "get", real)


models_with({"data": [{"id": "m"}]})
models_with({"data": [{"id": "x/m"}, {"id": "other", "extra": 1}]})
for body in ([], {"data": "x"}, {"data": [1]}, {"data": [{"id": None}]}):
    try:
        models_with(body)
        raise AssertionError(f"expected LLMError for {body}")
    except LLMError as e:
        assert "unexpected /models response" in str(e), e
try:
    models_with({"data": []})
    raise AssertionError("expected LLMError")
except LLMError as e:
    assert "not available" in str(e)

print("ok")
