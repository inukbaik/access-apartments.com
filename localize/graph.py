"""Walking graph over scan positions.

Matterport's `anchor.neighbors` lists scan positions linked to each one (4 to 44 per position in
Rabinowitz Hall), which looks like line of sight rather than "next to". We keep a neighbor link
only when both ends are on the same floor and within WALK_LINK_M meters.

Floors connect only where the scan does (stairs or elevator); routing comes later (TASKS lane B).
"""
import numpy as np

WALK_LINK_M = 8.0  # max length of one walking edge
NEAR_M = 4.0  # "same spot" radius: matches this close together are not a real confusion


class WalkGraph:
    def __init__(self, index, link_m=WALK_LINK_M):
        self.index = index
        n = len(index.panos)
        self.adj = [dict() for _ in range(n)]
        for i, p in enumerate(index.panos):
            for nid in p["neighbors"]:
                j = index.by_id.get(nid)
                if j is None or index.floor[i] != index.floor[j]:
                    continue
                d = float(np.linalg.norm(index.pos[i] - index.pos[j]))
                if d <= link_m:
                    self.adj[i][j] = d
                    self.adj[j][i] = d

    def dist(self, i, j):
        return float(np.linalg.norm(self.index.pos[i] - self.index.pos[j]))

    def near(self, i, radius=NEAR_M):
        """Scan positions on the same floor within `radius` meters of i (including i)."""
        idx = self.index
        d = np.linalg.norm(idx.pos - idx.pos[i], axis=1)
        same_floor = np.array([f == idx.floor[i] for f in idx.floor])
        return np.where((d <= radius) & same_floor)[0]

    def near_xy(self, i, radius=NEAR_M):
        """Scan positions within `radius` meters of i in x/y, on any floor (including i)."""
        d = np.linalg.norm(self.index.pos[:, :2] - self.index.pos[i, :2], axis=1)
        return np.where(d <= radius)[0]

    def reachable_within(self, i, hops=2):
        """Scan positions within `hops` walking edges of i (including i)."""
        seen, frontier = {i}, {i}
        for _ in range(hops):
            frontier = {j for k in frontier for j in self.adj[k]} - seen
            seen |= frontier
        return seen
