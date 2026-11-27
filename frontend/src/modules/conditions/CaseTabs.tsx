/**
 * **해석 케이스 탭** — 케이스가 있는 조건(v2)에서 리본 위에 선다. 탭을 고르면 아래의 트리 · 3D · 창이 그 케이스를
 * 그린다(공유 칸 — 선택 그룹 · 재료 · 접촉 · 메시 · 좌표계 — 은 케이스마다 같다).
 *
 * 케이스끼리의 규칙은 서버가 저장할 때 막는다(`conditions/cases.py` — 앞 케이스는 앞에 적힌 것만, 사슬만, 사슬 안의
 * 대상 솔버 · 구속 · 중력은 같다, 조인 볼트에 예압을 다시 적지 않는다). 여기서는 그 규칙을 처음부터 지키게 돕는다:
 * 「이어지는 케이스 추가」 는 해석 설정 · 구속 · 중력을 옮긴 사본이고, 이미 뒤가 있는 케이스에는 더하지 않는다.
 *
 * 케이스가 없는 조건(v1)에는 탭이 없다 — 지금과 같다. 케이스가 둘 이상이면 해석 쪽이 v2 를 받을 때까지 DOE 로
 * 내보낼 수 없어서(「정적 → 모달」 · 「볼트 예압 → 외력」 사슬만 서버가 v1 한 벌로 접는다), 케이스를 처음 만드는 일은 아직
 * API · MCP 로 한다.
 */

import { Layers } from 'lucide-react'

import { followerOf, followingCase, renamed } from '@/modules/conditions/cases'
import type { CaseItem } from '@/modules/conditions/cases'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'

/** 대상 솔버로 고를 이름 — 받는 쪽 능력표의 `solver`(SimEngBay, 2026-11-26). 비면 받는 쪽 작업의 솔버. */
const SOLVERS = [
  { key: '', label: '작업의 솔버를 따름' },
  { key: 'calculix', label: 'CalculiX' },
  { key: 'ansys', label: 'Ansys' },
]

interface Props {
  cases: CaseItem[]
  active: number
  /** 조건 창이 열려 있으면 케이스를 바꾸지 못한다 — 창의 조건이 어느 케이스의 것인지 흐려진다. */
  locked?: boolean
  onSelect: (index: number) => void
  /** 케이스 목록이 바뀌었다 — 함께 고를 케이스(새로 더한 것 · 지운 뒤 남은 것). */
  onChange: (cases: CaseItem[], active: number) => void
}

export function CaseTabs({ cases, active, locked, onSelect, onChange }: Props) {
  const current = cases[active]
  if (!current) return null
  const follower = followerOf(cases, active)
  const solver = current.target?.solver ?? ''
  /** 앞 케이스로 고를 수 있는 것 — 앞에 적힌 것 중 뒤가 비었거나 이 케이스인 것(사슬만). */
  const befores = cases.slice(0, active).filter((one, i) => {
    const after = followerOf(cases, i)
    return !after || after.name === current.name || one.name === current.depends_on
  })
  const patch = (next: Partial<CaseItem>) => onChange(cases.map((one, i) => (i === active ? { ...one, ...next } : one)), active)

  return (
    <div className="space-y-2 rounded-md border px-3 py-2 text-xs" aria-label="해석 케이스">
      <div className="flex flex-wrap items-center gap-1" role="tablist" aria-label="해석 케이스 목록">
        <Layers className="text-muted-foreground mr-1 size-4" aria-hidden />
        <span className="text-muted-foreground mr-1">해석 케이스</span>
        {cases.map((one, index) => (
          <button
            key={`${index}-${one.name}`}
            type="button"
            role="tab"
            aria-selected={index === active}
            disabled={locked && index !== active}
            title={one.depends_on ? `‘${one.depends_on}’의 끝 상태에서 시작합니다.` : '처음 상태에서 시작합니다.'}
            className={`rounded border px-2 py-0.5 disabled:opacity-40 ${
              index === active ? 'border-primary bg-accent font-medium' : 'text-muted-foreground hover:bg-accent/50'
            }`}
            onClick={() => onSelect(index)}
          >
            {one.depends_on ? '↳ ' : ''}
            {one.name || '(이름 없음)'}
          </button>
        ))}
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="ml-1 h-6 px-2 text-xs"
          disabled={locked || !!follower}
          title={
            follower
              ? `‘${current.name}’ 뒤에는 이미 ‘${follower.name}’이(가) 있습니다. 케이스는 사슬로만 잇습니다.`
              : `‘${current.name}’의 끝 상태에서 시작하는 케이스를 더합니다. 해석 설정 · 구속 · 중력을 옮기고, 나머지 하중은 새로 적습니다.`
          }
          onClick={() => {
            const next = [...cases]
            next.splice(active + 1, 0, followingCase(cases, active))
            onChange(next, active + 1)
          }}
        >
          이어지는 케이스 추가
        </Button>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex items-center gap-1.5">
          케이스 이름
          <Input
            aria-label="케이스 이름"
            className="h-7 w-40 text-xs"
            value={current.name}
            disabled={locked}
            onChange={(e) => onChange(renamed(cases, active, e.target.value), active)}
          />
        </label>
        <label className="flex items-center gap-1.5">
          앞 케이스
          <select
            aria-label="앞 케이스"
            className="bg-background rounded border px-1.5 py-0.5"
            value={current.depends_on ?? ''}
            disabled={locked}
            onChange={(e) => patch({ depends_on: e.target.value })}
          >
            <option value="">없음 — 처음 상태에서 시작</option>
            {befores.map((one) => (
              <option key={one.name} value={one.name}>
                {one.name}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-1.5">
          대상 솔버
          <select
            aria-label="대상 솔버"
            className="bg-background rounded border px-1.5 py-0.5"
            value={solver}
            disabled={locked}
            onChange={(e) => patch({ target: { ...current.target, solver: e.target.value } })}
          >
            {SOLVERS.map((one) => (
              <option key={one.key} value={one.key}>
                {one.label}
              </option>
            ))}
            {!SOLVERS.some((one) => one.key === solver) && <option value={solver}>{solver}</option>}
          </select>
        </label>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="ml-auto h-7 text-xs"
          disabled={locked || cases.length < 2 || !!follower}
          title={
            follower
              ? `‘${follower.name}’이(가) 이 케이스 뒤에 있습니다. 뒤 케이스를 먼저 삭제하거나 앞 케이스를 바꾸십시오.`
              : cases.length < 2
                ? '케이스가 하나뿐입니다.'
                : `‘${current.name}’ 케이스를 삭제합니다.`
          }
          onClick={() => onChange(cases.filter((_, i) => i !== active), Math.max(0, active - 1))}
        >
          케이스 삭제
        </Button>
      </div>

      {current.depends_on && (
        <p className="text-muted-foreground">
          ‘{current.depends_on}’의 끝 상태(변위 · 응력 · 접촉 상태)에서 시작합니다. 하중은 이어지지 않으므로 이 케이스에 걸 하중을 모두
          적으십시오. 앞에서 조인 볼트는 조인 길이로 잠기고, 구속과 중력은 앞 케이스와 같아야 합니다.
        </p>
      )}
      {cases.length > 1 && (
        <p className="text-amber-700 dark:text-amber-400">
          케이스가 둘 이상인 조건은 해석 쪽(SimEngBay)이 받을 수 있게 되기 전까지 DOE로 내보낼 수 없습니다. 예외는 「정적 → 모달」
          사슬(선응력 모달)과 「볼트 예압 → 외력」 정적 사슬(두 단계 정적)로, 한 해석으로 접어 내보냅니다. 첫 케이스에는 볼트 예압만,
          뒤 케이스에는 초기조건 없이 적고, 단계 수와 솔버는 기본값으로 두십시오.
        </p>
      )}
    </div>
  )
}
