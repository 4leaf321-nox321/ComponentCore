/**
 * 재료 한 벌의 물성값 — **내보낼 단위계로 바꾼 값**(`converted`)을 그대로 보인다. 물성 탐색기(고를 때)와
 * 해석 조건의 모델 트리(담아 둔 뒤)가 함께 쓴다.
 *
 * **환산은 서버가 한다.** 여기서 또 계산하면 환산표가 두 벌(파이썬 · TS)이 되고, 어느 날 어긋나면 화면이
 * 보여 준 값과 내보낸 값이 달라진다. 서버는 보여 줄 때와 내보낼 때 같은 함수를 쓴다 — 그래서 눈으로
 * 검산한 값이 그대로 나간다.
 *
 * 조용히 틀리지 않게 세 가지를 말한다: 구조 해석에 필요한 탄성계수 · 푸아송비 · 밀도가 빠졌다, 단위를 못
 * 바꿨다, 줄에 **표준 열쇠**가 없다(받는 쪽이 「어느 것이 탄성계수인가」 를 이름이 아니라 열쇠로 찾는다).
 */

import type { MaterialConverted } from '@/modules/materials/api'

/** 숫자를 읽을 만하게 — 아주 크거나 작으면 지수로. `7.85e-9` 은 `0.00000000785` 보다 낫다. */
export function show(value: number): string {
  if (!Number.isFinite(value)) return '?'
  const size = Math.abs(value)
  if (size !== 0 && (size >= 1e6 || size < 1e-3)) return value.toExponential(4)
  return String(Number(value.toPrecision(6)))
}

type Property = NonNullable<MaterialConverted['properties']>[number]

/** 물성 한 줄을 사람의 말로 — 온도별 점을 나란히(온도를 모르는 점은 「?」). */
export function propertyText(one: Pick<Property, 'unit' | 'points'>): string {
  const points = one.points ?? []
  const unit = one.unit ?? ''
  if (points.length <= 1) return `${show(points[0]?.value ?? NaN)} ${unit}`.trim()
  return points.map((p) => `${p.temperature_C ?? '?'} °C ${show(p.value ?? NaN)} ${unit}`.trim()).join(' · ')
}

/** 해석에 그대로 넘기면 틀리는 것 — 트리의 ⚠ 표시와 툴팁에 쓴다. 없으면 빈 목록. */
export function materialProblems(converted: MaterialConverted | null | undefined): string[] {
  if (!converted) return []
  const out: string[] = []
  if ((converted.missing_structural ?? []).length > 0) out.push(`구조 해석에 필요한 항목 누락: ${(converted.missing_structural ?? []).join(', ')}`)
  if ((converted.unconverted ?? []).length > 0) out.push(`단위를 변환하지 못한 항목: ${(converted.unconverted ?? []).join(', ')}`)
  return out
}

export function MaterialProperties({ converted, poisson }: { converted: MaterialConverted | null | undefined; poisson?: number | null }) {
  const poissonRatio = converted?.poisson_ratio ?? poisson
  return (
    <dl className="space-y-2 p-1">
      <div>
        <dt className="text-muted-foreground text-xs">밀도</dt>
        <dd className="text-sm">{converted?.density === undefined ? '(없음)' : `${show(converted.density)} ${converted.density_unit ?? ''}`}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground text-xs">푸아송비</dt>
        <dd className="text-sm">{poissonRatio ?? '(없음)'}</dd>
      </div>
      {(converted?.properties ?? []).map((one, index) => (
        <div key={index}>
          <dt className="text-muted-foreground flex flex-wrap items-baseline gap-1 text-xs">
            <span>{one.item}</span>
            {/* 출처 등급 — 1 이 가장 좋다. 4 를 1 인 줄 알고 쓰면 안 된다. */}
            {one.tier !== undefined && <span className="opacity-70">tier {one.tier}</span>}
            {/* 표준 열쇠가 없으면 받는 쪽이 이 줄이 무엇인지 이름으로만 짐작한다. */}
            {!one.key && (
              <span className="text-amber-700 dark:text-amber-400" title="물성 사전에 없는 이름이라 표준 열쇠(예: mechanical.youngs_modulus)가 붙지 않았습니다. 해석 쪽이 이 항목을 알아보지 못할 수 있습니다.">
                열쇠 없음
              </span>
            )}
          </dt>
          <dd className="text-sm break-words">{propertyText(one)}</dd>
          {/*
            **조건이 값의 일부다.** 「85°C/85%RH 168hr」 에서 잰 흡습률을 상온 값으로 쓰면 틀린다 — 안
            보이면 그것을 알 길이 없다.
          */}
          {one.conditions && Object.keys(one.conditions).length > 0 && (
            <dd className="text-muted-foreground text-xs break-words">
              {Object.entries(one.conditions)
                .map(([key, value]) => `${key} ${String(value)}`)
                .join(' · ')}
            </dd>
          )}
        </div>
      ))}
      {/*
        **해석에 바로 쓸 수 있나.** 탄성계수 · 푸아송비 · 밀도 중 빠진 것이 있으면 해석이 기본값(구조용
        강)으로 풀고, 그 사실은 고유진동수가 틀린 뒤에야 드러난다. 문헌 2663건 중 탄성계수를 가진 것은
        1025건이다.
      */}
      {(converted?.missing_structural ?? []).length > 0 ? (
        <p className="rounded border border-amber-300 bg-amber-50 p-1 text-xs text-amber-800 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-300">
          ⚠ 구조 해석에 필요한 항목 누락: {(converted?.missing_structural ?? []).join(', ')}. 이 상태로 전달하면 해석에서 기본값으로 계산합니다.
        </p>
      ) : (
        converted?.properties && <p className="text-xs text-emerald-700 dark:text-emerald-400">✓ 탄성계수, 푸아송비, 밀도가 모두 있습니다.</p>
      )}
      {/* **못 바꾼 것은 못 바꿨다고 말한다.** 조용히 원래 값을 보여 주면 그것이 새 단위인 줄 알고 그대로 쓴다. */}
      {(converted?.unconverted ?? []).length > 0 && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          ⚠ 단위를 변환하지 못한 항목: {(converted?.unconverted ?? []).join(', ')}. 값은 원래 단위로 표시됩니다.
        </p>
      )}
    </dl>
  )
}
