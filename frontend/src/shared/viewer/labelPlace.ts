/**
 * 치수 글자의 자리 — **화면에서 자(치수선)의 옆으로** 비켜 세운다.
 *
 * 글자를 자 한가운데에 두었더니 짧은 치수(벽 1.5 · 두께 2)에서 글자 상자가 화살표를 덮어 무엇을
 * 잰 것인지 안 보였다(2026-11-17 사용자 지적). 그래서 글자 상자가 자와 **겹치지 않을 만큼** 자에
 * 직각으로, 형상 가운데에서 먼 쪽으로 민다. 카메라를 돌리면 자가 화면에 놓이는 방향이 바뀌므로
 * 그릴 때마다 정한다(뷰어의 그리기 고리).
 *
 * 답은 `THREE.Sprite.center` — 글자 상자에서 기준점(자의 가운데)이 놓일 자리의 비율이다. 상자
 * 높이 단위로 셈하므로 확대 · 축소와 무관하다.
 */

/** 글자 상자와 자 사이의 틈 — 상자 높이의 몇 배. */
const GAP = 0.3

/**
 * `a` · `b` 는 자의 두 끝, `away` 는 형상 가운데 — 셋 다 **화면 픽셀**(가로 · 세로 같은 단위).
 * `aspect` 는 글자 상자의 가로 / 세로.
 */
export function labelCenter(a: [number, number], b: [number, number], away: [number, number], aspect: number): [number, number] {
  let dx = b[0] - a[0]
  let dy = b[1] - a[1]
  const length = Math.hypot(dx, dy)
  // 자가 화면에서 점이 되면(끝에서 본다) 그냥 위로.
  let nx = 0
  let ny = 1
  if (length > 1e-6) {
    dx /= length
    dy /= length
    nx = -dy
    ny = dx
  }
  // 형상 가운데에서 먼 쪽 — 안쪽에 두면 글자가 형상 위에 얹힌다.
  const mx = (a[0] + b[0]) / 2 - away[0]
  const my = (a[1] + b[1]) / 2 - away[1]
  if (nx * mx + ny * my < 0) {
    nx = -nx
    ny = -ny
  }
  // 상자의 반폭을 자의 직각 방향으로 잰 것 + 틈 — 이만큼 밀면 상자가 자에 안 닿는다.
  const reach = (aspect / 2) * Math.abs(nx) + 0.5 * Math.abs(ny) + GAP
  return [0.5 - (nx * reach) / aspect, 0.5 - ny * reach]
}
