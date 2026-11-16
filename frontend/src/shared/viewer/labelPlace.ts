/**
 * 치수 글자의 자리 — **화면에서 자(치수선)의 옆으로** 비켜 세우고, **글자끼리 겹치지 않게**
 * 편다.
 *
 * 글자를 자 한가운데에 두었더니 짧은 치수(벽 1.5 · 두께 2)에서 글자 상자가 화살표를 덮어 무엇을
 * 잰 것인지 안 보였다(2026-11-17 사용자 지적). 그래서 글자 상자가 자와 **겹치지 않을 만큼** 자에
 * 직각으로, 형상 가운데에서 먼 쪽으로 민다(`labelCenter`).
 *
 * 변수가 열 개인 도면에서 치수를 다 보이면 가까운 변수끼리(차축 · 바닥) 글자가 포개졌다(같은 날
 * 지적). 그래서 그린 순서대로 하나씩 놓으면서, 앞의 글자와 겹치면 자에서 조금 더 멀리 · 자를 따라
 * 옆으로 옮겨 본다(`spreadLabels`). 다 겹치면 처음 자리에 둔다 — 안 보이게 숨기는 것보다 낫다.
 *
 * 카메라를 돌리면 화면 위의 자리가 바뀌므로 그릴 때마다 정한다(뷰어의 그리기 고리). 답은
 * `THREE.Sprite.center` — 글자 상자에서 기준점이 놓일 자리의 비율이다.
 */

type Vec2 = [number, number]

/** 글자 상자와 자 사이의 틈 — 상자 높이의 몇 배. */
const GAP = 0.3
/** 글자끼리의 틈(픽셀). */
const SPACING = 3

/**
 * 자의 화면 방향 — `normal` 은 자에 직각이고 형상 가운데에서 먼 쪽, `tangent` 는 자를 따라.
 * 자가 화면에서 점이면(끝에서 본다) 위 · 오른쪽.
 */
export function rulerSide(a: Vec2, b: Vec2, away: Vec2): { normal: Vec2; tangent: Vec2 } {
  let dx = b[0] - a[0]
  let dy = b[1] - a[1]
  const length = Math.hypot(dx, dy)
  if (length <= 1e-6) return { normal: [0, 1], tangent: [1, 0] }
  dx /= length
  dy /= length
  let nx = -dy
  let ny = dx
  // 형상 가운데에서 먼 쪽 — 안쪽에 두면 글자가 형상 위에 얹힌다.
  const mx = (a[0] + b[0]) / 2 - away[0]
  const my = (a[1] + b[1]) / 2 - away[1]
  if (nx * mx + ny * my < 0) {
    nx = -nx
    ny = -ny
  }
  return { normal: [nx, ny], tangent: [dx, dy] }
}

/**
 * `a` · `b` 는 자의 두 끝, `away` 는 형상 가운데 — 셋 다 **화면 픽셀**(가로 · 세로 같은 단위).
 * `aspect` 는 글자 상자의 가로 / 세로. 상자 높이 단위로 셈하므로 확대 · 축소와 무관하다.
 */
export function labelCenter(a: Vec2, b: Vec2, away: Vec2, aspect: number): Vec2 {
  const [nx, ny] = rulerSide(a, b, away).normal
  // 상자의 반폭을 자의 직각 방향으로 잰 것 + 틈 — 이만큼 밀면 상자가 자에 안 닿는다.
  const reach = (aspect / 2) * Math.abs(nx) + 0.5 * Math.abs(ny) + GAP
  return [0.5 - (nx * reach) / aspect, 0.5 - ny * reach]
}

/** 화면 위 글자 하나 — 기준점(픽셀), 상자 크기(픽셀), 처음 자리(`center`), 밀 방향. */
export interface LabelBox {
  anchor: Vec2
  width: number
  height: number
  center: Vec2
  /** 먼저 밀어 볼 방향 — 자에서 멀어지는 쪽. */
  normal: Vec2
  /** 다음에 밀어 볼 방향 — 자를 따라. */
  tangent: Vec2
}

interface Rect {
  left: number
  right: number
  bottom: number
  top: number
}

function rectOf(box: LabelBox, center: Vec2): Rect {
  const left = box.anchor[0] - center[0] * box.width
  const bottom = box.anchor[1] - center[1] * box.height
  return { left, right: left + box.width, bottom, top: bottom + box.height }
}

function overlaps(a: Rect, b: Rect): boolean {
  return a.left < b.right + SPACING && b.left < a.right + SPACING && a.bottom < b.top + SPACING && b.bottom < a.top + SPACING
}

/** 밀어 볼 자리 — (자에서 멀리, 자를 따라) 상자 높이 · 폭 단위. 가까운 것부터. */
const TRIES: Vec2[] = [0, 1.15, 2.3, 3.45, 4.6].flatMap((out) => [0, 0.6, -0.6, 1.2, -1.2].map((along): Vec2 => [out, along]))

/**
 * 글자들을 **겹치지 않게** — 앞에서부터 하나씩 놓고, 앞의 것과 겹치면 `TRIES` 의 자리를 차례로
 * 본다. 답은 글자마다 `center`.
 */
export function spreadLabels(boxes: LabelBox[]): Vec2[] {
  const placed: Rect[] = []
  return boxes.map((box) => {
    let chosen = box.center
    for (const [out, along] of TRIES) {
      const dx = box.normal[0] * out * box.height + box.tangent[0] * along * box.width
      const dy = box.normal[1] * out * box.height + box.tangent[1] * along * box.width
      const center: Vec2 = [box.center[0] - dx / box.width, box.center[1] - dy / box.height]
      const rect = rectOf(box, center)
      if (!placed.some((other) => overlaps(rect, other))) {
        chosen = center
        break
      }
    }
    placed.push(rectOf(box, chosen))
    return chosen
  })
}
