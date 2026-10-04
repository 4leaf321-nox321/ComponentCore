/**
 * 지그 생성기가 알아본 특징(`kind:role`)과 로케이터 종류의 이름 — 서버 `core/model.py` 의
 * `Feature` · `LocatorSpec` 과 같은 말. 열쇠(`plane:bottom`)를 그대로 보이면 사람이 못 읽는다.
 */

const FEATURES: Record<string, string> = {
  'plane:bottom': '바닥면',
  'plane:underside': '아랫면',
  'plane:top': '윗면',
  'plane:step': '단차면',
  'plane:side': '옆면',
  'plane:slope_up': '경사면(위)',
  'plane:slope_down': '경사면(아래)',
  'hole:through': '관통 구멍',
  'hole:blind': '막힌 구멍',
  'hole:side_through': '옆 관통 구멍',
  'hole:side_blind': '옆 막힌 구멍',
  'hole:side_angled': '비스듬한 옆 구멍',
  'boss:vertical': '보스',
  'boss:side': '옆 보스',
  'pocket:top': '포켓(위)',
  'pocket:bottom': '포켓(아래)',
}

export const LOCATOR_LABELS: Record<string, string> = { pin: '위치 핀', rest: '받침대', side_pin: '측면 핀' }

export function featureLabel(key: string): string {
  return FEATURES[key] ?? key
}

/** 특징 개수를 한 줄로 — 「바닥면 1 · 옆 관통 구멍 1 · 포켓(위) 1」. */
export function featureLine(counts: Record<string, number>): string {
  return Object.entries(counts)
    .map(([key, count]) => `${featureLabel(key)} ${count}`)
    .join(' · ')
}

/** 로케이터를 종류마다 세어 한 줄로 — 「위치 핀 1 · 측면 핀 1」. */
export function locatorLine(locators: { kind: string }[]): string {
  const counts = new Map<string, number>()
  for (const one of locators) counts.set(one.kind, (counts.get(one.kind) ?? 0) + 1)
  return [...counts].map(([kind, count]) => `${LOCATOR_LABELS[kind] ?? kind} ${count}`).join(' · ')
}

/** 규격 부품표를 한 줄로 — 「SUP-16 받침 × 4 · PIN-8.4 위치 핀 × 2」. */
export function bomLine(rows: { part_no: string; name: string; count: number }[]): string {
  return rows.map((one) => `${one.part_no} ${one.name} × ${one.count}`).join(' · ')
}
