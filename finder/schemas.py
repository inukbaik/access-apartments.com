"""Type and shape checks for the data we get from outside APIs (pydantic v2).

Only types, shapes and finiteness are checked. Null is "no data" and stays legal wherever
`checks.py` already treats a value as optional. Range rules (negative or implausible values) are NOT
here: `checks.py` reports those as "bad measurement". Unknown extra fields are ignored.

Use `validate(Model, data, "Matterport model abc")`. It returns nothing and raises `DataError` with a
short message naming the source and the first failing field paths. Callers keep using the original
dict; the models are never used to rewrite data.
"""
import math
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from pydantic_core import PydanticCustomError


class DataError(ValueError):
    """Data from an API or a cache file does not have the expected shape."""


# A real, finite number. int is fine, str and bool are not.
Num = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


# ------------------------------------------------------------------ error messages
_REASONS = {
    "float_type": "a number", "int_type": "a number", "float_parsing": "a number",
    "string_type": "a string", "bool_type": "true or false", "list_type": "a list",
    "dict_type": "an object", "model_type": "an object", "model_attributes_type": "an object",
}


def _got(v: Any) -> str:
    return "null" if v is None else type(v).__name__


def _reason(err: Any) -> str:
    t = err["type"]
    if t == "missing":
        return "field is missing"
    if t == "finite_number":
        return "expected a finite number, got NaN or infinity"
    if t in _REASONS:
        return f"expected {_REASONS[t]}, got {_got(err.get('input'))}"
    if t == "too_short":
        return "list is empty"
    return str(err["msg"])[:100]


def validate(model: type[BaseModel], data: Any, what: str) -> None:
    """Raise DataError("<what>: <path>: <reason>; ...") if `data` does not fit `model`."""
    try:
        model.model_validate(data)
    except ValidationError as e:
        errs = e.errors()
        parts = [f"{'.'.join(str(p) for p in er['loc']) or '(top level)'}: {_reason(er)}" for er in errs[:3]]
        more = f" (+{len(errs) - 3} more)" if len(errs) > 3 else ""
        raise DataError(f"{what}: " + "; ".join(parts) + more) from None


# ------------------------------------------------------------------ Matterport screening (matterport.QUERY)
class Classification(_Base):
    label: str | None = None
    confidence: Num | None = None


class Dimensions(_Base):
    areaFloor: Num | None = None
    width: Num | None = None
    depth: Num | None = None
    height: Num | None = None


class Edge(_Base):
    id: str | None = None


class Boundary(_Base):
    edges: list[Edge] | None = None


class Room(_Base):
    id: str | None = None
    classifications: list[Classification] | None = None
    dimensions: Dimensions | None = None
    boundary: Boundary | None = None


class Opening(_Base):
    type: str | None = None
    label: str | None = None
    width: Num | None = None
    height: Num | None = None
    lowerElevation: Num | None = None


class FloorEdge(_Base):
    id: str | None = None
    type: str | None = None
    thickness: Num | None = None
    openings: list[Opening] | None = None


class Floor(_Base):
    id: str | None = None
    label: str | None = None
    edges: list[FloorEdge] | None = None


class ScreenModel(_Base):
    id: str | None = None
    name: str | None = None
    rooms: list[Room] | None = None
    floors: list[Floor] | None = None


# ------------------------------------------------------------------ Matterport evidence (evidence.QUERY)
class XY(_Base):
    x: Num
    y: Num


class Vertex(_Base):
    position: XY


class EvOpening(_Base):
    id: str | None = None
    type: str | None = None
    width: Num | None = None
    relativeCenter: Num | None = None


class EvEdge(_Base):
    id: str
    type: str | None = None
    vertices: list[Vertex] | None = None
    openings: list[EvOpening] | None = None


class EvFloor(_Base):
    id: str
    label: str | None = None
    edges: list[EvEdge] | None = None


class XYZ(_Base):
    x: Num
    y: Num
    z: Num | None = None


class Quaternion(_Base):
    x: Num
    y: Num
    z: Num
    w: Num


class FloorRef(_Base):
    id: str | None = None


class Anchor(_Base):
    floor: FloorRef | None = None


class Skybox(_Base):
    status: str | None = None
    children: list[str] | None = None


class Pano(_Base):
    id: str
    label: str | None = None
    position: XYZ
    rotation: Quaternion | None = None
    anchor: Anchor | None = None
    skybox: Skybox | None = None  # present in a fresh response; removed before caching
    has_sky: bool | None = None  # added by evidence.fetch, present in cache files


class EvidenceModel(_Base):
    id: str | None = None
    name: str | None = None
    floors: list[EvFloor] | None = None
    panoLocations: list[Pano] | None = None


# ------------------------------------------------------------------ Vexcel property/extract
def _check(d: dict[str, Any], dotted: str, kinds: tuple[type, ...], label: str) -> None:
    """The value at a dotted key (flat "a.b" or nested {"a": {"b": ...}}) must be null or one of `kinds`."""
    cur: Any = d
    while True:
        if not isinstance(cur, dict):
            return
        if dotted in cur:
            v = cur[dotted]
            break
        head, _, rest = dotted.partition(".")
        if not rest:
            return
        cur, dotted = cur.get(head), rest
    if v is None:
        return
    ok = isinstance(v, kinds) and (bool in kinds or not isinstance(v, bool))
    want = {bool: "true or false", str: "a string", float: "a number"}[kinds[-1]]
    if not ok:
        raise PydanticCustomError("bad_value", "{key}: expected {want}, got {got}",
                                  {"key": label, "want": want, "got": _got(v)})
    if isinstance(v, float) and not math.isfinite(v):
        raise PydanticCustomError("bad_value", "{key}: expected a finite number, got NaN or infinity",
                                  {"key": label})


class VexStructure(_Base):
    @model_validator(mode="before")
    @classmethod
    def _shape(cls, d: Any) -> Any:
        if isinstance(d, dict):
            _check(d, "footprint.wkt", (str,), "footprint.wkt")
            _check(d, "roof-characteristics.height", (int, float), "roof-characteristics.height")
        return d


class VexProperties(_Base):
    structures: list[VexStructure] | None = None

    @model_validator(mode="before")
    @classmethod
    def _shape(cls, d: Any) -> Any:
        if isinstance(d, dict):
            _check(d, "metadata.is-ortho-image", (bool,), "metadata.is-ortho-image")
            _check(d, "metadata.ortho-date-estimate", (str,), "metadata.ortho-date-estimate")
            _check(d, "metadata.collection", (str,), "metadata.collection")
        return d


class VexFeature(_Base):
    properties: VexProperties | None = None


class VexResponse(_Base):
    features: list[VexFeature] | None = None


class HeightResult(_Base):
    """The cached result of vexcel.building_height / select_height."""
    status: Literal["ok", "unavailable"]
    height_m: Num | None
    photo_date: str | None
    collection: str | None
    reason: str


# ------------------------------------------------------------------ LLM (OpenAI-compatible)
class ModelEntry(_Base):
    id: str = ""


class ModelsResponse(_Base):
    data: list[ModelEntry] = []


class ToolFunction(_Base):
    name: str
    arguments: Any = None  # a JSON string, an object, or null depending on the server


class ToolCall(_Base):
    id: str | None = None
    function: ToolFunction


class Message(_Base):
    content: Any = None  # checked by llm.chat: must be text or empty
    tool_calls: list[ToolCall] | None = None


class Choice(_Base):
    message: Message


class ChatResponse(_Base):
    choices: list[Choice] = Field(min_length=1)
