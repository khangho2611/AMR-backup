"""Known-free grid planning, independent of ROS and hardware.

Clearance is the configured enclosing body radius plus a wall margin; neither
is inferred from wheel track or a drawing. Unknown space and map edges block
the whole footprint. Returned paths contain cell centres and never shortcuts.
"""
import heapq
import math
import time
from collections import deque


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def twist_centres(v, w, horizon=.5, spatial_step=.005):
    """Sample the centre's constant-twist path in the current base frame.

    Half the distance between samples is added to the enclosing footprint by
    callers, so an obstacle between samples cannot be skipped. This is a local
    command horizon, not a measured physical braking-distance guarantee.
    """
    if (not all(finite(x) for x in (v,w,horizon,spatial_step)) or
            abs(v) > .08 or abs(w) > .35 or not 0 < horizon <= .5 or spatial_step <= 0):
        return None
    steps=max(1,math.ceil(abs(v)*horizon/spatial_step))
    if steps > 1000:return None
    centres=[]
    for k in range(steps+1):
        t=horizon*k/steps
        if abs(w) < 1e-9:
            centres.append((v*t,0.))
        else:
            centres.append((v/w*math.sin(w*t),v/w*(1-math.cos(w*t))))
    return centres,abs(v)*horizon/(2*steps)


def slam_censored_ranges(ranges, range_min, range_max, threshold=12.):
    """Preserve no-hit rays for Karto without inventing obstacle endpoints.

    Karto discards +inf and readings >= range_max. Encode only explicit +inf
    below range_max but above its raytrace threshold; endpoints stay invalid.
    Invalid/NaN beams and actual obstacle ranges are left unchanged.
    """
    if (not all(finite(v) for v in (range_min,range_max,threshold)) or
            not 0 <= range_min < threshold < range_max-.02):
        raise ValueError('SLAM censor threshold must be below sensor maximum')
    return [range_max-.01 if r == math.inf else r for r in ranges]


class GridPlanner:
    def __init__(self, width, height, resolution, origin, data, body_radius,
                 margin=.15, budget_s=.15):
        if (type(width) is not int or type(height) is not int or
                width <= 0 or height <= 0 or width * height > 2_000_000 or
                not finite(resolution) or resolution < .001 or resolution > 1 or
                len(origin) != 3 or not all(finite(v) for v in origin) or
                not finite(body_radius) or not 0 < body_radius <= 2. or
                not finite(margin) or not 0 <= margin <= 1. or
                not finite(budget_s) or budget_s <= 0 or
                len(data) != width * height or
                any(type(v) is not int or not -1 <= v <= 100 for v in data)):
            raise ValueError('Invalid map or unconfigured body radius')
        self.w, self.h, self.res = width, height, resolution
        self.origin, self.data = tuple(origin), tuple(data)
        self.body_radius = body_radius
        self.radius = body_radius + margin
        self.budget_s = budget_s
        self.safe = bytearray(width * height)
        self._inflate()

    def _inflate(self):
        deadline = time.monotonic() + self.budget_s
        r = self.radius
        cells = math.ceil(r / self.res + .5)
        if (2*cells+1)**2 > 1_000_000:
            raise ValueError('Costmap resolution/footprint exceeds work budget')
        # Distance to the square occupied/unknown cell, not just its centre.
        offsets = [(dx, dy) for dy in range(-cells, cells+1)
                   for dx in range(-cells, cells+1)
                   if math.hypot(max(0, abs(dx)-.5)*self.res,
                                 max(0, abs(dy)-.5)*self.res) <= r]
        for y in range(self.h):
            if time.monotonic() > deadline:
                raise TimeoutError('Costmap build deadline')
            for x in range(self.w):
                i = y*self.w+x
                edge = min(x+.5, y+.5, self.w-x-.5, self.h-y-.5)*self.res
                self.safe[i] = self.data[i] == 0 and edge > r
        # Adjacent blocked cells have overlapping inflation intervals. Merge
        # them into runs and clear each row slice in C, keeping the exact same
        # square-cell distance mask without a Python loop per covered cell.
        spans={}
        for dx,dy in offsets:
            spans[dy]=max(spans.get(dy,0),abs(dx))
        for y in range(self.h):
            if time.monotonic() > deadline:
                raise TimeoutError('Costmap build deadline')
            start=None
            runs=[]
            for x in range(self.w):
                blocked=self.data[y*self.w+x] != 0
                if blocked and start is None:start=x
                elif not blocked and start is not None:
                    runs.append((start,x-1));start=None
            if start is not None:runs.append((start,self.w-1))
            for dy,dx in spans.items():
                ny=y+dy
                if not 0 <= ny < self.h:continue
                base=ny*self.w
                for left,right in runs:
                    a=max(0,left-dx);b=min(self.w,right+dx+1)
                    self.safe[base+a:base+b]=b'\0'*(b-a)

    def world_to_cell(self, x, y):
        if not finite(x) or not finite(y):
            return None
        ox, oy, yaw = self.origin
        c, s = math.cos(yaw), math.sin(yaw)
        dx, dy = x-ox, y-oy
        a = math.floor((c*dx+s*dy)/self.res)
        b = math.floor((-s*dx+c*dy)/self.res)
        return (a, b) if 0 <= a < self.w and 0 <= b < self.h else None

    def cell_to_world(self, x, y):
        ox, oy, yaw = self.origin
        a, b = (x+.5)*self.res, (y+.5)*self.res
        c, s = math.cos(yaw), math.sin(yaw)
        return ox+c*a-s*b, oy+s*a+c*b

    def traversable(self, cell):
        return (cell is not None and 0 <= cell[0] < self.w and
                0 <= cell[1] < self.h and bool(self.safe[cell[1]*self.w+cell[0]]))

    def swept_clear(self, pose, v, w):
        """Check the whole moving disk against exact blocked-cell rectangles.

        Evaluate the actual subcell pose, rather than snapping it to a safe cell
        centre. Occupied, unknown and map edges all retain the configured margin.
        """
        if len(pose) != 3 or not all(finite(x) for x in pose):return False
        samples=twist_centres(v,w,spatial_step=self.res/4)
        if samples is None:return False
        centres,padding=samples
        r=self.radius+padding
        ox,oy,yaw=self.origin
        c,s=math.cos(yaw),math.sin(yaw)
        pc,ps=math.cos(pose[2]),math.sin(pose[2])
        deadline=time.monotonic()+min(self.budget_s,.025)
        for bx,by in centres:
            wx,wy=pose[0]+pc*bx-ps*by,pose[1]+ps*bx+pc*by
            px,py=c*(wx-ox)+s*(wy-oy),-s*(wx-ox)+c*(wy-oy)
            if min(px,py,self.w*self.res-px,self.h*self.res-py) <= r:return False
            left,right=math.floor((px-r)/self.res),math.floor((px+r)/self.res)
            low,high=math.floor((py-r)/self.res),math.floor((py+r)/self.res)
            for y in range(low,high+1):
                if time.monotonic()>deadline:return False
                for x in range(left,right+1):
                    if self.data[y*self.w+x] == 0:continue
                    dx=max(x*self.res-px,0.,px-(x+1)*self.res)
                    dy=max(y*self.res-py,0.,py-(y+1)*self.res)
                    if math.hypot(dx,dy) <= r:return False
        return True

    def escape_swept_clear(self, pose, v, w):
        """Leave an existing clearance-margin violation without entering collision.

        The normal A* margin stays unchanged. This recovery is available only
        when already inside that margin: the enclosing body must remain wholly
        known-free, minimum clearance cannot decrease, and the endpoint must
        improve it. Unknown cells and map boundaries remain obstacles.
        """
        if len(pose)!=3 or not all(finite(x) for x in pose) or v==0:return False
        samples=twist_centres(v,w,spatial_step=min(.005,self.res/4))
        if samples is None:return False
        centres,padding=samples
        ox,oy,yaw=self.origin
        c,s=math.cos(yaw),math.sin(yaw)
        pc,ps=math.cos(pose[2]),math.sin(pose[2])
        deadline=time.monotonic()+min(self.budget_s,.025)
        clearances=[]
        for bx,by in centres:
            wx,wy=pose[0]+pc*bx-ps*by,pose[1]+ps*bx+pc*by
            px,py=c*(wx-ox)+s*(wy-oy),-s*(wx-ox)+c*(wy-oy)
            clearance=min(self.radius+.01,px,py,self.w*self.res-px,self.h*self.res-py)
            if clearance<=self.body_radius+padding:return False
            search=self.radius+.01
            for y in range(max(0,math.floor((py-search)/self.res)),min(self.h-1,math.floor((py+search)/self.res))+1):
                if time.monotonic()>deadline:return False
                for x in range(max(0,math.floor((px-search)/self.res)),min(self.w-1,math.floor((px+search)/self.res))+1):
                    if self.data[y*self.w+x]==0:continue
                    dx=max(x*self.res-px,0.,px-(x+1)*self.res)
                    dy=max(y*self.res-py,0.,py-(y+1)*self.res)
                    clearance=min(clearance,math.hypot(dx,dy))
            if clearance<=self.body_radius+padding:return False
            if clearances and clearance<clearances[-1]-1e-7:return False
            clearances.append(clearance)
        return clearances[0]<self.radius and clearances[-1]>clearances[0]+.0001

    def neighbours(self, cell):
        x, y = cell
        for dx, dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
            nxt = (x+dx, y+dy)
            if not self.traversable(nxt):
                continue
            if dx and dy and (not self.traversable((x+dx,y)) or
                              not self.traversable((x,y+dy))):
                continue
            yield nxt, math.hypot(dx,dy)

    def path(self, start_world, goal_world):
        start, goal = self.world_to_cell(*start_world), self.world_to_cell(*goal_world)
        if not self.traversable(start) or not self.traversable(goal):
            return None
        deadline = time.monotonic()+self.budget_s
        heap, cost, parent = [(0., 0., start)], {start: 0.}, {}
        while heap:
            if time.monotonic() > deadline:
                return None
            _, g, here = heapq.heappop(heap)
            if g > cost[here]:
                continue
            if here == goal:
                result = [here]
                while here in parent:
                    here = parent[here]
                    result.append(here)
                return [self.cell_to_world(*p) for p in reversed(result)]
            for nxt, step in self.neighbours(here):
                ng = g+step
                if ng < cost.get(nxt, math.inf):
                    cost[nxt], parent[nxt] = ng, here
                    heuristic = math.hypot(nxt[0]-goal[0], nxt[1]-goal[1])
                    heapq.heappush(heap, (ng+heuristic, ng, nxt))
        return None

    def frontiers(self, start_world, excluded=(), rejected=()):
        """Safe viewpoints for reachable raw frontiers. None = invalid/timeout.

        BFS on known-free cells finds raw reachable frontiers; viewpoints are
        then placed on safe cells with a known-free sight line to that boundary.
        This permits standoff from unknown without driving the body into it.
        """
        start = self.world_to_cell(*start_world)
        if not self.traversable(start):
            return None
        deadline = time.monotonic()+self.budget_s
        reachable, costs, q = {start}, {start: 0}, deque([start])
        while q:
            if time.monotonic() > deadline:
                return None
            here = q.popleft()
            for nxt, _ in self.neighbours(here):
                if nxt not in reachable:
                    reachable.add(nxt); costs[nxt] = costs[here]+1; q.append(nxt)
        raw_seen, raw_q, boundary = {start}, deque([start]), []
        while raw_q:
            if time.monotonic() > deadline:
                return None
            x, y = raw_q.popleft()
            is_frontier = False
            for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nx, ny = x+dx, y+dy
                if not 0 <= nx < self.w or not 0 <= ny < self.h:
                    continue
                value = self.data[ny*self.w+nx]
                if value == -1:
                    is_frontier = True
                elif value == 0 and (nx,ny) not in raw_seen:
                    raw_seen.add((nx,ny)); raw_q.append((nx,ny))
            if is_frontier:
                boundary.append((x,y))
        # Adjacent frontier pixels are one region, not dozens of new goals.
        max_cells = math.ceil(self.radius/self.res)+3
        regions, remaining, wide_regions = {}, set(boundary), set()
        region = 0
        while remaining:
            seed = min(remaining)
            remaining.remove(seed)
            component = deque([seed]); regions[seed] = region
            lo_x=hi_x=seed[0];lo_y=hi_y=seed[1]
            while component:
                if time.monotonic() > deadline:
                    return None
                x,y = component.popleft()
                lo_x,hi_x=min(lo_x,x),max(hi_x,x)
                lo_y,hi_y=min(lo_y,y),max(hi_y,y)
                for dx,dy in ((1,0),(-1,0),(0,1),(0,-1),(1,1),(1,-1),(-1,1),(-1,-1)):
                    nxt = (x+dx,y+dy)
                    if nxt in remaining:
                        remaining.remove(nxt);regions[nxt]=region;component.append(nxt)
            # A frontier can wrap around several walls as one connected ring.
            # Split that component by viewing direction rather than rejecting
            # the whole perimeter when one direction gets stuck.
            if hi_x-lo_x > 2*max_cells and hi_y-lo_y > 2*max_cells:
                wide_regions.add(region)
            region += 1
        candidates = {}
        # Multi-source wave avoids scanning a footprint-sized square for every
        # frontier pixel on every ROS tick.
        wave = deque((p,p,0) for p in boundary)
        seen = set(boundary)
        while wave:
            if time.monotonic() > deadline:
                return None
            p,bound,depth = wave.popleft()
            if p in reachable:
                wx,wy = self.cell_to_world(*p)
                if (math.hypot(wx-start_world[0],wy-start_world[1]) >= max(self.res*2,.10) and
                        self.segment_known_free(p,bound)):
                    rid=regions[bound]
                    sector=round(math.atan2(wy-start_world[1],wx-start_world[0])/(math.pi/4))%8 if rid in wide_regions else None
                    candidates[p] = (costs[p],(rid,sector))
            if depth >= max_cells:
                continue
            for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
                nxt=(p[0]+dx,p[1]+dy)
                if nxt in raw_seen and nxt not in seen:
                    seen.add(nxt);wave.append((nxt,bound,depth+1))
        rejected_regions = {rid for p,(cost,rid) in candidates.items()
                            if any(math.dist(self.cell_to_world(*p),(x,y)) < r for x,y,r in rejected)}
        def priority(p):
            wx,wy=self.cell_to_world(*p)
            heading=math.atan2(wy-start_world[1],wx-start_world[0])
            novelty=min((abs((heading-math.atan2(y-start_world[1],x-start_world[0])+math.pi)%(2*math.pi)-math.pi)
                         for x,y,r in rejected),default=0.)
            return (-novelty,candidates[p][0],p)
        representatives = {}
        for p in sorted(candidates,key=priority):
            rid=candidates[p][1]
            wx,wy = self.cell_to_world(*p)
            if rid not in rejected_regions and not any(math.hypot(wx-ex,wy-ey) < er for ex,ey,er in excluded):
                representatives.setdefault(rid,p)
        ordered = sorted(representatives.values(),key=priority)
        return {'goals': [self.cell_to_world(*p) for p in ordered],
                'reachable_frontiers': len({rid for cost,rid in candidates.values()}),
                'unknown_cells': self.data.count(-1)}

    def segment_known_free(self, a, b):
        steps = max(abs(a[0]-b[0]),abs(a[1]-b[1]))*4+1
        last = a
        for k in range(steps+1):
            x = math.floor(a[0]+.5+(b[0]-a[0])*k/steps)
            y = math.floor(a[1]+.5+(b[1]-a[1])*k/steps)
            if not 0 <= x < self.w or not 0 <= y < self.h or self.data[y*self.w+x] != 0:
                return False
            if x != last[0] and y != last[1]:
                if self.data[y*self.w+last[0]] != 0 or self.data[last[1]*self.w+x] != 0:
                    return False
            last = (x,y)
        return True
