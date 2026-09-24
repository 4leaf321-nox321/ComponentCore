/**
 * 렌더러의 캔버스를 **담는 칸에 꼭 맞게** 붙인다 — 3D 뷰어 셋이 같은 규칙을 쓴다.
 *
 * `renderer.setSize(w, h, false)` 는 그리는 픽셀(w·dpr × h·dpr)만 정하고 CSS 크기는 두지
 * 않는다. 그러면 캔버스가 **제 픽셀 수를 CSS 크기로** 삼아, 배율 125 % · 150 % 화면에서 칸보다
 * 크게 놓이고 넘친 만큼 잘린다 — 형상이 확대된 채 오른쪽 아래로 밀려, 아래쪽이 잘려 보인다
 * (실측 2026-09-24, 헤드리스 크로미움: 664×567 칸에 830×708 캔버스, 408×547 칸에 612×820).
 *
 * **절대 위치로 칸을 덮는다.** 크기만 100 % 로 두면 칸의 높이가 정해지지 않은 자리에서 캔버스가
 * 다시 칸의 크기에 끼어들고, 잴 때마다 dpr 배로 커지거나 줄어든다.
 */
export function mountCanvas(container: HTMLElement, canvas: HTMLCanvasElement) {
  canvas.style.position = 'absolute'
  canvas.style.inset = '0'
  canvas.style.width = '100%'
  canvas.style.height = '100%'
  container.appendChild(canvas)
}
