"""Run: .venv/bin/python finder/test_buildings.py  (made-up data only)"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from finder.buildings import group_buildings, street_key  # noqa: E402


def u(name, address="", pid="", lat=10.0, lon=20.0):
    return {"name": name, "address": address, "costar_property_id": pid, "lat": lat, "lon": lon}


def names(groups):
    return sorted(sorted(x["name"] for x in g) for g in groups)


# street_key: variants and unit suffixes agree; junk is rejected
assert street_key("12 West Oak Street, Town, CA 90000") == street_key("12 W Oak St #4, Town, CA")
assert street_key("12 W Oak St Unit 4") == "12 w oak"
assert street_key("1348 West 35th Street") == street_key("1348 W 35th St") == "1348 w 35"
assert street_key("1288 3 W 35") == street_key("1288 W 35th Pl") == "1288 w 35"
assert street_key("1288 3 W 35th Pl, Los Angeles, CA, 90007, US") == "1288 w 35"
assert street_key("1288 W 35th Pl") != street_key("1286 1/2 W 35th Pl")
assert street_key("1286 1/2 W 35th Pl") == "1286 1/2 w 35"
for bad in ("", None, "US", "Studio", "1 Br, 1 Ba", "4BR, 4BA", "2BR, 1BA - 860SF", "Oak Street", "1286 1/2 - F"):
    assert street_key(bad) is None, bad

# sub-building numbers keep structures apart even though street_key ignores them
g = group_buildings([u("x1", "1288 1 W 35th Pl"), u("x2", "1288 2 W 35th Pl"), u("x3a", "1288 3 W 35"),
                     u("x3b", "1288 3 W 35th Pl, LA"), u("plain", "1288 W 35th Pl")])
assert names(g) == [["plain"], ["x1"], ["x2"], ["x3a", "x3b"]], g

# same street_key but 300 m apart: data error, stay separate
g = group_buildings([u("a", "12 W Oak St", lat=10.0), u("b", "12 W Oak St", lat=10.0027)])
assert len(g) == 2, g
# key from the name when the address is missing; unit letters dropped
g = group_buildings([u("1288 3 - B", lat=10.0), u("1288 3 - C", lat=10.0001), u("1288 1 - A"), u("1286 1/2 - F")])
assert names(g) == [["1286 1/2 - F"], ["1288 1 - A"], ["1288 3 - B", "1288 3 - C"]], g

# same address groups even when the coordinates differ; different address stays apart
g = group_buildings([u("a", "12 W Oak St, T", lat=10.0), u("b", "12 West Oak Street, T", lat=10.001),
                     u("c", "14 W Oak St, T", lat=10.0)])
assert names(g) == [["a", "b"], ["c"]], g

# address beats costar id; costar id used when there is no address
g = group_buildings([u("a", "12 W Oak St", "p1"), u("b", "14 W Oak St", "p1"), u("c", "", "p2"), u("d", "US", "p2")])
assert names(g) == [["a"], ["b"], ["c", "d"]], g

# name prefix: same building within 50 m (~30 m apart), no address
a = u("Elm 5 - A", lat=10.0, lon=20.0)
b = u("Elm 5 - B", lat=10.00027, lon=20.0)  # ~30 m
assert names(group_buildings([a, b])) == [["Elm 5 - A", "Elm 5 - B"]]
# same prefix but far apart (~1 km): two buildings
far = u("Elm 5 - C", lat=10.01, lon=20.0)
assert len(group_buildings([a, b, far])) == 2

# adjacent buildings 20 m apart with different names stay separate
x = u("Elm 5 - A", lat=10.0)
y = u("Elm 7 - A", lat=10.00018)  # ~20 m
assert len(group_buildings([x, y])) == 2

# proximity fallback: no name pattern, no address
p = u("Loft", lat=10.0)
q = u("Loft 2", lat=10.00009)  # ~10 m
r = u("Loft 3", lat=10.0003)  # ~33 m from q: separate
assert names(group_buildings([p, q, r])) == [["Loft", "Loft 2"], ["Loft 3"]]
print("ok")
