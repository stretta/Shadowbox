from __future__ import annotations

from dataclasses import dataclass, field


BRICK_PANEL_TRIGGER_PRESSES = 4
BRICK_PANEL_BASE_FPS = 20.0


@dataclass
class BrickPanelGame:
    brick_rows: int = 4
    brick_cols: int = 8
    lives: int = 3
    score: int = 0
    level: int = 1
    paddle_center: float = 0.5
    paddle_width: float = 0.2
    paddle_y: float = 0.92
    ball_x: float = 0.5
    ball_y: float = 0.88
    ball_dx: float = 0.022
    ball_dy: float = -0.028
    ball_radius: float = 0.015
    launched: bool = False
    game_over: bool = False
    bricks: list[list[bool]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.bricks:
            self.reset()

    @property
    def brick_top(self) -> float:
        return 0.08

    @property
    def brick_bottom(self) -> float:
        return 0.36

    @property
    def brick_gap(self) -> float:
        return 0.01

    @property
    def paddle_left(self) -> float:
        return self.paddle_center - (self.paddle_width / 2.0)

    @property
    def paddle_right(self) -> float:
        return self.paddle_center + (self.paddle_width / 2.0)

    @property
    def status_text(self) -> str:
        if self.game_over:
            return "press to retry"
        if not self.launched:
            return "press to launch"
        return ""

    def reset(self) -> None:
        self.lives = 3
        self.score = 0
        self.level = 1
        self.game_over = False
        self._reset_round()
        self._reset_bricks()

    def rotate(self, step: int) -> None:
        if step == 0:
            return
        self.paddle_center = min(0.88, max(0.12, self.paddle_center + (0.04 * step)))
        if not self.launched:
            self.ball_x = self.paddle_center
            self.ball_y = self.paddle_y - 0.04

    def press(self) -> None:
        if self.game_over:
            self.reset()
            return
        if not self.launched:
            self.launched = True

    def update(self, frame_scale: float = 1.0) -> None:
        if self.game_over:
            return
        if not self.launched:
            self.ball_x = self.paddle_center
            self.ball_y = self.paddle_y - 0.04
            return

        frame_scale = max(0.0, float(frame_scale))
        next_x = self.ball_x + (self.ball_dx * frame_scale)
        next_y = self.ball_y + (self.ball_dy * frame_scale)

        if next_x - self.ball_radius <= 0.0:
            next_x = self.ball_radius
            self.ball_dx = abs(self.ball_dx)
        elif next_x + self.ball_radius >= 1.0:
            next_x = 1.0 - self.ball_radius
            self.ball_dx = -abs(self.ball_dx)

        if next_y - self.ball_radius <= 0.0:
            next_y = self.ball_radius
            self.ball_dy = abs(self.ball_dy)

        if self._hit_brick(next_x, next_y):
            self.ball_dy *= -1.0
            next_y = self.ball_y + self.ball_dy

        paddle_top = self.paddle_y - 0.02
        if (
            self.ball_dy > 0
            and (next_y + self.ball_radius) >= paddle_top
            and (next_y - self.ball_radius) <= (self.paddle_y + 0.02)
            and self.paddle_left <= next_x <= self.paddle_right
        ):
            offset = (next_x - self.paddle_center) / max(0.001, self.paddle_width / 2.0)
            self.ball_dx = max(-0.06, min(0.06, offset * 0.052))
            self.ball_dy = -max(0.032, min(0.064, abs(self.ball_dy)))
            next_y = paddle_top - self.ball_radius

        if next_y - self.ball_radius >= 1.0:
            self.lives -= 1
            if self.lives <= 0:
                self.game_over = True
                self.launched = False
                return
            self._reset_round()
            return

        self.ball_x = next_x
        self.ball_y = next_y

    def _reset_round(self) -> None:
        self.paddle_center = 0.5
        self.paddle_width = max(0.072, (0.2 - ((self.level - 1) * 0.01)) * 0.6)
        self.ball_x = self.paddle_center
        self.ball_y = self.paddle_y - 0.04
        self.ball_dx = 0.044 if self.level % 2 else -0.044
        self.ball_dy = -min(0.068, (0.028 + ((self.level - 1) * 0.002)) * 2.0)
        self.launched = False

    def _reset_bricks(self) -> None:
        self.bricks = [[True for _ in range(self.brick_cols)] for _ in range(self.brick_rows)]

    def _hit_brick(self, next_x: float, next_y: float) -> bool:
        if not (self.brick_top <= next_y <= self.brick_bottom):
            return False

        brick_h = (self.brick_bottom - self.brick_top) / self.brick_rows
        row = int((next_y - self.brick_top) / brick_h)
        if row < 0 or row >= self.brick_rows:
            return False

        brick_w = 1.0 / self.brick_cols
        col = int(next_x / brick_w)
        if col < 0 or col >= self.brick_cols:
            return False

        if not self.bricks[row][col]:
            return False

        self.bricks[row][col] = False
        self.score += 10 * self.level

        if not any(any(row_items) for row_items in self.bricks):
            self.level += 1
            self._reset_bricks()
            self._reset_round()

        return True
