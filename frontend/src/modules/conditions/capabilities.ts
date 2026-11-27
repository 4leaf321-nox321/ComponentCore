/**
 * **받는 쪽 능력표** — 케이스의 대상 솔버로 고를 이름(해석 확장 설계 5장).
 *
 * 표는 서버가 들고 있는 복사본이다(`/cad/conditions/capabilities` — 시스템 관리자가 ‘서버’ 화면에서 SimEngBay 로부터
 * 갱신한다). 거르기(받지 않는 항목 · 읽지 않는 칸 · 안내)는 서버가 한다 — 저장 · DOE 생성은 막고, 준비 점검은 식 알림과
 * 같은 길(`/cad/conditions/notes` 에 대상 솔버를 실어)로 받는다. 여기는 솔버 목록만 만든다.
 */

/** 솔버 한 장 — 화면이 읽는 칸만. 나머지(해석별 항목 · 칸)는 서버가 거르는 데 쓴다. */
export interface CapabilityTable {
  solver: string
  version?: string | null
  receiver?: string
  receiver_version?: string
}

export interface SolverOption {
  key: string
  label: string
}

/** 사람이 읽는 솔버 이름 — 모르는 이름은 그대로. */
const SOLVER_LABELS: Record<string, string> = { calculix: 'CalculiX', ansys: 'Ansys' }

/** 능력표가 오기 전(받은 적이 없을 때)의 목록 — 받는 쪽이 지금 받는 둘(SimEngBay, 2026-11-26). */
const FALLBACK = ['calculix', 'ansys']

export const FOLLOW_JOB = '작업의 솔버를 따름'

/**
 * 대상 솔버 목록 — 비움(받는 쪽 작업의 솔버) + 복사본의 솔버(판이 있으면 함께). 복사본이 없으면 아는 둘. 지금 값이
 * 목록에 없으면 「능력표에 없음」 을 붙여 남긴다 — 고르지 않은 값을 화면이 지우면 안 된다.
 */
export function solverOptions(tables: CapabilityTable[] | null | undefined, current = ''): SolverOption[] {
  const listed = tables ? tables.map((one) => one.solver) : FALLBACK
  const out: SolverOption[] = [{ key: '', label: FOLLOW_JOB }]
  for (const key of listed) {
    const table = tables?.find((one) => one.solver === key)
    const name = SOLVER_LABELS[key] ?? key
    out.push({ key, label: table?.version ? `${name} ${table.version}` : name })
  }
  if (current && !listed.includes(current)) {
    out.push({ key: current, label: tables ? `${current} (능력표에 없음)` : current })
  }
  return out
}
