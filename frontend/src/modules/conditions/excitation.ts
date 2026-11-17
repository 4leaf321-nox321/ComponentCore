/**
 * 가진 프로파일의 셈 — 표를 붙여 넣은 글에서 읽고, 가속도 PSD 의 실효값(Grms)을 낸다.
 *
 * Grms 는 서버도 낸다(`conditions.psd_grms` — 내보낼 때 하중에 싣는다). 화면은 표를 고치는 동안
 * 바로 보여 주려고 같은 식을 들고 있다 — 규격이 함께 적는 「Grms 6.06」 과 맞춰 보며 표를 넣는다.
 * 두 쪽 시험이 같은 예(평평한 0.04 g²/Hz, 20 ~ 2000 Hz → √79.2)를 본다.
 */

export type Cell = number | string
export type Row = [Cell, Cell]

/** 수 · `=식` — 빈칸은 빈칸. */
export function cellOf(text: string): Cell {
  const trimmed = text.trim()
  if (trimmed === '' || trimmed.startsWith('=')) return trimmed
  const num = Number(trimmed)
  return Number.isFinite(num) ? num : trimmed
}

/**
 * 엑셀 · 표에서 복사한 글 → 행들. 줄마다 탭 · 쉼표 · 세미콜론 · 공백으로 나눈 **앞 두 칸**.
 * 수가 아닌 줄(머리글 「Hz  g²/Hz」)은 건너뛴다. 천 단위 쉼표(「1,000」)는 칸 구분으로 읽히므로
 * 쓰지 않는다 — 주파수 표에는 거의 없다.
 */
export function pasteRows(text: string): Row[] {
  const rows: Row[] = []
  for (const line of text.split(/\r?\n/)) {
    const parts = line.split(/[\t;,\s]+/).filter(Boolean)
    if (parts.length < 2) continue
    const a = cellOf(parts[0])
    const b = cellOf(parts[1])
    if (typeof a === 'number' && typeof b === 'number') rows.push([a, b])
  }
  return rows
}

/**
 * 가속도 PSD 표의 실효값(g) — 구간마다 로그-로그 직선(`P ∝ f^n`)의 면적을 더한 제곱근.
 * 식이 섞였거나 수가 맞지 않으면 `null`.
 */
export function psdGrms(rows: Row[]): number | null {
  if (rows.length < 2) return null
  let area = 0
  for (let i = 0; i + 1 < rows.length; i++) {
    const [f1, p1] = rows[i]
    const [f2, p2] = rows[i + 1]
    if (typeof f1 !== 'number' || typeof p1 !== 'number' || typeof f2 !== 'number' || typeof p2 !== 'number') return null
    if (f1 <= 0 || f2 <= f1 || p1 <= 0 || p2 <= 0) return null
    const n = Math.log(p2 / p1) / Math.log(f2 / f1)
    area += Math.abs(n + 1) < 1e-9 ? p1 * f1 * Math.log(f2 / f1) : ((p1 * f1) / (n + 1)) * ((f2 / f1) ** (n + 1) - 1)
  }
  return Math.sqrt(area)
}

/** (m/s²)²/Hz → g²/Hz 의 나눗수 — 9.80665² ≈ 96.17. */
export const G_SQUARED = 9.80665 ** 2

/**
 * IEC 60068-2-64 는 PSD 를 (m/s²)²/Hz 로 적는다. 조건 · 내보내기는 늘 g²/Hz 이므로 값 열을 9.80665² 로
 * 나눈다(유효숫자 여섯). 식 · 빈칸은 그대로 둔다.
 */
export function toG2(rows: Row[]): Row[] {
  return rows.map(([frequency, value]): Row => [frequency, typeof value === 'number' ? Number((value / G_SQUARED).toPrecision(6)) : value])
}
