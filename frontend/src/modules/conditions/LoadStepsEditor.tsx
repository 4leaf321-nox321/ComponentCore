/**
 * **하중 단계 · 수렴 제어 · 출력 요청** — 정적 해석 케이스의 ② 칸(해석 확장 설계 8장, SimEngBay 와 정함 2026-11-27).
 * 해석 설정 창의 사양표 칸 아래에 선다.
 *
 * - 서버 사양표는 이 칸들을 감춰 둔다(목록 · 묶음이라 사양표 폼이 그리지 못한다). 여기서 그린다.
 * - 점검은 서버가 저장할 때 한다(`conditions/steps.py` — 끝 시간이 늘어나는가, 부단계가 최소 ≤ 처음 ≤ 최대인가).
 * - **해석 케이스에서만** 쓴다. 케이스가 없는 조건이면 부르는 쪽이 「해석 케이스로 나누기」 를 보인다.
 * - 대변형은 단계가 아니라 위의 ‘대변형’ 칸이 정한다(두 솔버 모두 단계마다 켜고 끄지 못한다).
 */

import { Plus, X } from 'lucide-react'

import type { ConditionItem } from '@/modules/conditions/api'
import { NumberText } from '@/modules/conditions/NumberText'
import { Button } from '@/shared/components/ui/button'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

interface Substeps {
  initial?: number | string | null
  minimum?: number | string | null
  maximum?: number | string | null
}

export interface LoadStep {
  name?: string
  end_time?: number | string | null
  substeps?: Substeps
}

interface Convergence {
  force_tolerance?: number | string | null
  displacement_tolerance?: number | string | null
  max_iterations?: number | string | null
  line_search?: string
  stabilization?: string
}

interface Outputs {
  quantities?: string[]
  at?: string | { count?: number | string }
}

/** 출력 요청의 양 — 서버 `analysis.OUTPUT_QUANTITIES` 와 같은 차례. */
const QUANTITIES: [string, string][] = [
  ['displacement', '변위'],
  ['stress', '응력'],
  ['strain', '변형률'],
  ['equivalent_plastic_strain', '등가 소성 변형률'],
  ['reaction', '반력'],
  ['contact_pressure', '접촉 압력'],
  ['contact_status', '접촉 상태'],
]
/** 화면 기본 — 받는 쪽의 지금 기본과 같다(SimEngBay, 2026-11-27). 이 값이면 칸을 비운다(`null`). */
export const DEFAULT_QUANTITIES = ['displacement', 'stress', 'strain', 'reaction']

/** 단계의 이름 — 비우면 「단계 n」. */
export const stepLabel = (step: LoadStep | undefined, index: number) => `${index + 1}. ${String(step?.name ?? '') || `단계 ${index + 1}`}`

/** 하중 단계 목록 — 칸이 비었거나 모양이 아니면 빈 목록. */
export function stepsOf(analysis: ConditionItem | Record<string, unknown> | undefined): LoadStep[] {
  const steps = analysis?.load_steps
  return Array.isArray(steps) ? (steps as LoadStep[]) : []
}

/** `12` → 12, `=식` → 그대로, 빈칸 → null(받는 쪽 기본). */
function valueOf(text: string): number | string | null {
  const trimmed = text.trim()
  if (trimmed === '') return null
  if (trimmed.startsWith('=')) return trimmed
  const num = Number(trimmed)
  return Number.isFinite(num) ? num : trimmed
}

function SmallNumber({ label, value, onChange, placeholder }: { label: string; value: unknown; onChange: (v: number | string | null) => void; placeholder?: string }) {
  return <NumberText aria-label={label} className="h-7 w-20 px-1.5 text-xs" value={value} placeholder={placeholder} onText={(text) => onChange(valueOf(text))} />
}

export function LoadStepsEditor({
  analysis,
  chained = false,
  onChange,
}: {
  analysis: ConditionItem
  /** 다른 케이스와 이은 케이스인가 — 그러면 하중 단계를 쓰지 않는다(받는 쪽 첫 판). */
  chained?: boolean
  onChange: (next: ConditionItem) => void
}) {
  const steps = stepsOf(analysis)
  const convergence = (analysis.convergence ?? {}) as Convergence
  const outputs = (analysis.outputs ?? null) as Outputs | null
  const quantities = outputs?.quantities ?? DEFAULT_QUANTITIES
  const at = outputs?.at ?? 'step_end'
  const atKind = typeof at === 'object' ? 'count' : at

  const setSteps = (next: LoadStep[]) => {
    // 단계를 쓰면 v1 의 ‘하중 단계 수’ · ‘초기 부단계 수’ 는 비운다(서버가 섞임을 막는다). 처음 단계로 나눌 때 적어 둔
    // 초기 부단계 수는 첫 단계의 처음 값으로 옮긴다.
    const out: ConditionItem = { ...analysis, load_steps: next }
    if (next.length > 0) {
      if (steps.length === 0 && analysis.substeps != null && next[0]) {
        next[0] = { ...next[0], substeps: { ...next[0].substeps, initial: analysis.substeps as number | string } }
      }
      out.steps = 1
      out.substeps = null
    }
    onChange(out)
  }
  const setStep = (index: number, patch: Partial<LoadStep>) => setSteps(steps.map((one, i) => (i === index ? { ...one, ...patch } : one)))
  const setSub = (index: number, key: keyof Substeps, value: number | string | null) =>
    setStep(index, { substeps: { ...steps[index]?.substeps, [key]: value } })

  const setConvergence = (patch: Partial<Convergence>) => {
    const next = { ...convergence, ...patch }
    const blank =
      next.force_tolerance == null &&
      next.displacement_tolerance == null &&
      next.max_iterations == null &&
      (next.line_search ?? 'program_controlled') === 'program_controlled' &&
      (next.stabilization ?? 'off') === 'off'
    onChange({ ...analysis, convergence: blank ? null : next })
  }
  const setOutputs = (nextQuantities: string[], nextAt: Outputs['at']) => {
    const plain = nextAt === 'step_end' && nextQuantities.length === DEFAULT_QUANTITIES.length && DEFAULT_QUANTITIES.every((one) => nextQuantities.includes(one))
    onChange({ ...analysis, outputs: plain ? null : { quantities: QUANTITIES.map(([key]) => key).filter((key) => nextQuantities.includes(key)), at: nextAt } })
  }

  return (
    <div className="space-y-4 border-t pt-3">
      <section className="space-y-2" aria-label="하중 단계">
        <div className="flex items-center justify-between">
          <Label>하중 단계</Label>
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-7 text-xs"
            disabled={chained}
            onClick={() => setSteps([...steps, { name: `단계 ${steps.length + 1}` }])}
          >
            <Plus className="mr-1 size-3.5" aria-hidden />
            단계 추가
          </Button>
        </div>
        {chained && (
          <p className="text-amber-700 dark:text-amber-400 text-xs">
            다른 케이스와 이은 케이스에서는 하중 단계를 쓰지 않습니다(해석 쪽 첫 판). 단계를 나누려면 이 케이스를 다른 케이스와 잇지
            마십시오.
          </p>
        )}
        <p className="text-muted-foreground text-xs">
          하중을 단계로 나누어 겁니다. 하중마다 거는 단계나 시간별 배율을 지정할 수 있습니다. 단계가 없으면 한 단계로 풉니다. 끝 시간은 하중 이력의
          눈금이며, 비워 두면 단계 번호(1, 2, …)입니다. 대변형은 위의 ‘대변형’ 칸이 정합니다.
        </p>
        {steps.length > 0 && (
          <table className="w-full text-xs">
            <thead className="text-muted-foreground">
              <tr>
                <th className="py-1 text-left font-normal">단계</th>
                <th className="py-1 text-left font-normal">이름</th>
                <th className="py-1 text-left font-normal">끝 시간(s)</th>
                <th className="py-1 text-left font-normal" colSpan={3}>
                  부단계 수(처음, 최소, 최대)
                </th>
                <th />
              </tr>
            </thead>
            <tbody>
              {steps.map((step, index) => (
                <tr key={index}>
                  <td className="text-muted-foreground pr-1 tabular-nums">{index + 1}</td>
                  <td className="pr-1">
                    <Input aria-label={`단계 ${index + 1} 이름`} className="h-7 px-1.5 text-xs" value={String(step.name ?? '')} onChange={(e) => setStep(index, { name: e.target.value })} />
                  </td>
                  <td className="pr-1">
                    <SmallNumber label={`단계 ${index + 1} 끝 시간`} value={step.end_time} placeholder={String(index + 1)} onChange={(v) => setStep(index, { end_time: v })} />
                  </td>
                  <td className="pr-1">
                    <SmallNumber label={`단계 ${index + 1} 부단계 처음`} value={step.substeps?.initial} placeholder="자동" onChange={(v) => setSub(index, 'initial', v)} />
                  </td>
                  <td className="pr-1">
                    <SmallNumber label={`단계 ${index + 1} 부단계 최소`} value={step.substeps?.minimum} placeholder="자동" onChange={(v) => setSub(index, 'minimum', v)} />
                  </td>
                  <td className="pr-1">
                    <SmallNumber label={`단계 ${index + 1} 부단계 최대`} value={step.substeps?.maximum} placeholder="자동" onChange={(v) => setSub(index, 'maximum', v)} />
                  </td>
                  <td>
                    <Button type="button" variant="ghost" size="sm" className="h-7 px-1.5" aria-label={`단계 ${index + 1} 삭제`} onClick={() => setSteps(steps.filter((_, i) => i !== index))}>
                      <X className="size-3.5" aria-hidden />
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <details className="space-y-2" open={analysis.convergence != null}>
        <summary className="cursor-pointer text-sm font-medium">수렴 제어</summary>
        <p className="text-muted-foreground text-xs">
          비워 두면 해석 쪽 기본값입니다. 판정 식이 솔버마다 달라 같은 값이라도 엄격함이 같지 않습니다.
        </p>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <label className="space-y-1">
            <span>힘 잔차 허용(비율)</span>
            <SmallNumber label="힘 잔차 허용" value={convergence.force_tolerance} placeholder="기본" onChange={(v) => setConvergence({ force_tolerance: v })} />
          </label>
          <label className="space-y-1">
            <span>변위 허용(비율)</span>
            <SmallNumber label="변위 허용" value={convergence.displacement_tolerance} placeholder="기본" onChange={(v) => setConvergence({ displacement_tolerance: v })} />
          </label>
          <label className="space-y-1">
            <span>평형 반복 상한</span>
            <SmallNumber label="평형 반복 상한" value={convergence.max_iterations} placeholder="기본" onChange={(v) => setConvergence({ max_iterations: v })} />
          </label>
          <label className="space-y-1">
            <span>선 탐색</span>
            <select
              aria-label="선 탐색"
              className="bg-background block h-7 rounded border px-1.5"
              value={convergence.line_search ?? 'program_controlled'}
              onChange={(e) => setConvergence({ line_search: e.target.value })}
            >
              <option value="program_controlled">프로그램 제어</option>
              <option value="on">켬</option>
              <option value="off">끔</option>
            </select>
          </label>
          <label className="space-y-1">
            <span>안정화</span>
            <select
              aria-label="안정화"
              className="bg-background block h-7 rounded border px-1.5"
              value={convergence.stabilization ?? 'off'}
              onChange={(e) => setConvergence({ stabilization: e.target.value })}
            >
              <option value="off">끔</option>
              <option value="on">켬</option>
            </select>
          </label>
        </div>
      </details>

      <details className="space-y-2" open={analysis.outputs != null}>
        <summary className="cursor-pointer text-sm font-medium">출력 요청</summary>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs" role="group" aria-label="저장할 값">
          {QUANTITIES.map(([key, label]) => (
            <label key={key} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={quantities.includes(key)}
                onChange={(e) => setOutputs(e.target.checked ? [...quantities, key] : quantities.filter((one) => one !== key), at)}
              />
              {label}
            </label>
          ))}
        </div>
        <div className="flex items-center gap-2 text-xs">
          <label className="flex items-center gap-1.5">
            저장 시점
            <select
              aria-label="저장 시점"
              className="bg-background h-7 rounded border px-1.5"
              value={atKind}
              onChange={(e) => setOutputs(quantities, e.target.value === 'count' ? { count: 10 } : e.target.value)}
            >
              <option value="step_end">단계 끝</option>
              <option value="all">모든 부단계</option>
              <option value="count">단계마다 횟수 지정</option>
            </select>
          </label>
          {typeof at === 'object' && (
            <SmallNumber label="저장 횟수" value={at.count} onChange={(v) => setOutputs(quantities, { count: v ?? 1 })} />
          )}
        </div>
        <p className="text-muted-foreground text-xs">반력은 구속마다 합하고, 접촉 압력과 접촉 상태는 접촉마다 저장합니다.</p>
      </details>
    </div>
  )
}
