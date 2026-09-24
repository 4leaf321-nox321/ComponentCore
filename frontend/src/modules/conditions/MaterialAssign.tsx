/**
 * 물성 하나를 **어느 바디에 적용할 것인가.**
 *
 * 대화상자가 아니라 옆 패널이다. 바디가 여럿인 조립에서 물성을 배분하려면 3D 를 보면서
 * 골라야 하는데, 모달이 뒤를 가리면 열고 닫기를 되풀이하게 된다. 여기서는 **목록에서
 * 클릭하거나 3D 에서 해당 바디를 클릭하면** 바로 지정된다.
 */

import type { Body } from '@/modules/conditions/api'
import type { MaterialItem } from '@/modules/conditions/api'
import { Badge } from '@/shared/components/ui/badge'
import { Button } from '@/shared/components/ui/button'
import { Label } from '@/shared/components/ui/label'

/** 모든 바디에 적용한다는 뜻의 이름 — 백엔드와 같은 말을 쓴다. */
const ALL = '전체'

export function MaterialAssign({
  material,
  bodies,
  decks,
  onChange,
  onRemove,
}: {
  material: MaterialItem | undefined
  bodies: Body[]
  /** 이 재료로 생성 가능한 솔버 덱 형식(`ready` 인 것만 표시한다). */
  decks: { key: string; ready: boolean }[]
  onChange: (next: Partial<MaterialItem>) => void
  onRemove: () => void
}) {
  if (!material) return null
  const ref = (material.ref ?? {}) as Record<string, unknown>
  const 적용 = String(material.apply_to ?? ALL)
  const 고른덱 = material.deck_formats ?? []
  const 가능한덱 = decks.filter((one) => one.ready)

  return (
    <div className="space-y-3">
      <div>
        <p className="font-medium">{String(ref.name ?? '이름 없음')}</p>
        <p className="text-muted-foreground text-xs">
          값은 물성 플랫폼이 제공한 그대로 전달됩니다 — 이 플랫폼이 수정하지 않습니다.
        </p>
      </div>

      <div className="space-y-1">
        <Label>적용 대상</Label>
        <p className="text-muted-foreground text-xs">
          3D 에서 바디를 클릭해도 지정됩니다.
        </p>
        <ul className="space-y-1">
          <li>
            <button
              type="button"
              aria-pressed={적용 === ALL}
              className={`w-full rounded border px-2 py-1 text-left text-sm ${
                적용 === ALL ? 'border-primary bg-accent' : 'hover:bg-accent/50'
              }`}
              onClick={() => onChange({ apply_to: ALL })}
            >
              전체
              {bodies.length > 1 && (
                <span className="text-muted-foreground ml-2 text-xs">바디 {bodies.length} 개</span>
              )}
            </button>
          </li>
          {/* 바디가 하나뿐이면 「전체」 와 같은 말이라 목록을 표시하지 않는다. */}
          {bodies.length > 1 &&
            bodies.map((one) => (
              <li key={one.name}>
                <button
                  type="button"
                  aria-pressed={적용 === one.name}
                  className={`w-full rounded border px-2 py-1 text-left text-sm ${
                    적용 === one.name ? 'border-primary bg-accent' : 'hover:bg-accent/50'
                  }`}
                  onClick={() => onChange({ apply_to: one.name })}
                >
                  {one.name}
                  {/* 체적을 함께 표시한다 — 이름이 비슷할 때 구분 근거가 된다. */}
                  {one.volume !== undefined && (
                    <span className="text-muted-foreground ml-2 text-xs">
                      {Math.round(one.volume).toLocaleString()} mm³
                    </span>
                  )}
                </button>
              </li>
            ))}
        </ul>
      </div>

      {가능한덱.length > 0 && (
        <div className="space-y-1">
          <Label>솔버 덱 포함</Label>
          <p className="text-muted-foreground text-xs">
            해석 플랫폼이 사용할 덱을 함께 전달합니다. 중립 물성은 그대로 전달되며 덱은 그
            옆에 추가됩니다.
          </p>
          <div className="flex flex-wrap gap-1">
            {가능한덱.map((one) => {
              const 선택됨 = 고른덱.includes(one.key)
              return (
                <button
                  key={one.key}
                  type="button"
                  aria-pressed={선택됨}
                  className={`rounded border px-2 py-0.5 text-xs ${
                    선택됨 ? 'border-primary bg-accent' : 'text-muted-foreground'
                  }`}
                  onClick={() =>
                    onChange({
                      deck_formats: 선택됨
                        ? 고른덱.filter((x) => x !== one.key)
                        : [...고른덱, one.key],
                    })
                  }
                >
                  {one.key}
                </button>
              )
            })}
          </div>
        </div>
      )}

      <div className="flex items-center gap-2">
        <Badge variant="outline" className="font-normal">
          {적용}
        </Badge>
        <Button size="sm" variant="ghost" className="ml-auto" onClick={onRemove}>
          제외
        </Button>
      </div>
    </div>
  )
}
