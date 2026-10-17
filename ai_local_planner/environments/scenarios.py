"""Six physically navigable training maps (metres, world coordinates)."""

from dataclasses import dataclass, field

import numpy as np


@dataclass
class Circle:
    x: float
    y: float
    radius: float
    vx: float = 0.0
    vy: float = 0.0
    anchor_x: float = field(init=False)
    anchor_y: float = field(init=False)

    def __post_init__(self):
        self.anchor_x, self.anchor_y = self.x, self.y


@dataclass
class Scenario:
    level: int
    bounds: tuple[float, float]
    start: tuple[float, float, float]
    goal: tuple[float, float]
    walls: list[tuple[float, float, float, float]] = field(default_factory=list)
    obstacles: list[Circle] = field(default_factory=list)

    def all_walls(self) -> np.ndarray:
        width, height = self.bounds
        boundary = [(0., 0., width, 0.), (width, 0., width, height),
                    (width, height, 0., height), (0., height, 0., 0.)]
        return np.asarray(boundary + self.walls, dtype=np.float64).reshape(-1, 4)


def create_scenario(level: int, rng: np.random.Generator) -> Scenario:
    """Sample starts, goals and obstacles with clearance for a 20 cm disk robot."""
    if level == 1:
        return Scenario(1, (10., 4.), (1., 2., 0.),
                        (float(rng.uniform(4., 8.)), float(rng.uniform(1.65, 2.35))))
    if level == 2:
        return Scenario(2, (10., 6.), (1., 3., 0.), (8., 3.),
                        obstacles=[Circle(float(rng.uniform(4., 5.5)),
                                          float(rng.uniform(2.85, 3.15)),
                                          float(rng.uniform(.15, .30)))])
    if level == 3:
        # 0.70 m wide L corridor, open only at entry/exit. Turn at (3.65, 1.85).
        walls = [(0., 1.5, 4., 1.5), (0., 2.2, 3.3, 2.2),
                 (3.3, 2.2, 3.3, 7.), (4., 1.5, 4., 7.)]
        return Scenario(3, (7., 7.), (1., 1.85, 0.), (3.65, 5.65), walls)
    if level == 4:
        obstacles = []
        for _ in range(int(rng.integers(6, 11))):
            for _attempt in range(100):
                x, y = float(rng.uniform(2., 8.)), float(rng.uniform(1., 9.))
                radius = float(rng.uniform(.16, .30))
                if all(np.hypot(x - o.x, y - o.y) > radius + o.radius + .35
                       for o in obstacles):
                    obstacles.append(Circle(x, y, radius))
                    break
            else:
                raise RuntimeError("Unable to place the requested cluttered obstacles")
        return Scenario(4, (10., 10.), (1., 5., 0.), (9., 5.), obstacles=obstacles)
    if level == 5:
        # A 1.2 m wide U with an open mouth at y=2.8. Robot faces the closed end.
        # With v>=0 it must rotate in place (clearance allows this), then exit.
        walls = [(3.2, 2.8, 3.2, 4.4), (3.2, 4.4, 4.4, 4.4),
                 (4.4, 4.4, 4.4, 2.8)]
        return Scenario(5, (8., 7.), (3.8, 3.65, np.pi / 2), (3.8, 1.0), walls)
    if level == 6:
        count = int(rng.integers(2, 4))
        obstacles = [Circle(x=float(x), y=float(rng.uniform(1.8, 5.8)),
                            radius=float(rng.uniform(.17, .27)),
                            vy=float(rng.choice([-1, 1]) * rng.uniform(.15, .25)))
                     for x in np.linspace(3., 7., count)]
        return Scenario(6, (10., 8.), (1., 4., 0.), (9., 4.),
                        obstacles=obstacles)
    raise ValueError(f"Invalid curriculum level {level}; expected 1..6")
