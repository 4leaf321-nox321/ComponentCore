/**
 * 주파수 표 칸 — 가진 프로파일(`[[주파수, 값], …]`). 행마다 두 칸, 행 추가 · 삭제, 그리고 **엑셀에서 두
 * 열을 복사해 붙여 넣기**: 빈 표면 아래 글 칸에, 표가 있으면 아무 칸에나 여러 행을 붙여 넣으면 표
 * 전체를 바꾼다. 규격의 프로파일은 수십 행이라 한 칸씩 치게 두면 틀린다. 가속도 PSD 면 실효값(Grms)을
 * 보인다 — 규격이 함께 적는 값과 맞춰 본다. IEC 60068-2-64 처럼 (m/s²)²/Hz 로 적힌 표는 「g²/Hz 로
 * 바꾸기」 로 나눈다 — 받는 쪽은 g²/Hz 만 받는다.
 *
 * 조건 창(하중의 주파수별 배율 · PSD 표)과 시험 규격의 사내 규격 편집(랜덤 진동의 PSD 표)이 함께 쓴다.
 */

import { useState } from 'react'

import { cellOf, pasteRows, psdGrms, toG2 } from '@/modules/conditions/excitation'
import type { Row } from '@/modules/conditions/excitation'
import { NumberText } from '@/modules/conditions/NumberText'
import { Button } from '@/shared/components/ui/button'
import { Label } from '@/shared/components/ui/label'
import { Textarea } from '@/shared/components/ui/textarea'

export interface FrequencyColumn {
  title: string
  unit?: string
}

const DEFAULT_COLUMNS: FrequencyColumn[] = [{ title: '주파수', unit: 'Hz' }, { title: '값' }]

export function FrequencyTable({
  title,
  columns = DEFAULT_COLUMNS,
  grms = false,
  description,
  value,
  onChange,
}: {
  title: string
  columns?: FrequencyColumn[]
  /** 가속도 PSD 표 — 실효값(Grms)을 보인다. */
  grms?: boolean
  description?: string
  value: unknown
  /** 빈 표는 `null`. */
  onChange: (next: Row[] | null) => void
}) {
  const rows: Row[] = Array.isArray(value) ? (value as Row[]) : []
  const [pasted, setPasted] = useState('')
  const put = (next: Row[]) => onChange(next.length > 0 ? next : null)
  const shown = grms ? psdGrms(rows) : null
  /** 여러 행(탭 · 줄바꿈)이 들어오면 표 전체를 바꾼다 — 한 칸 붙여넣기는 그 칸에 둔다. */
  const onPaste = (event: React.ClipboardEvent) => {
    const text = event.clipboardData.getData('text')
    if (!/[\t\n]/.test(text.trim())) return
    const got = pasteRows(text)
    if (got.length === 0) return
    event.preventDefault()
    put(got)
  }
  return (
    <div className="space-y-1">
      <Label>{title}</Label>
      {rows.length > 0 ? (
        <table className="w-full text-xs" onPaste={onPaste}>
          <thead>
            <tr>
              <th className="text-muted-foreground w-8 px-1 text-left font-normal">행</th>
              {columns.map((one) => (
                <th key={one.title} className="text-muted-foreground px-1 text-left font-normal">
                  {one.title}
                  {one.unit ? ` (${one.unit})` : ''}
                </th>
              ))}
              <th className="w-8">
                <span className="sr-only">삭제</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <tr key={index}>
                <td className="text-muted-foreground px-1">{index + 1}</td>
                {[0, 1].map((column) => (
                  <td key={column} className="px-0.5 py-0.5">
                    <NumberText
                      className="h-7 text-xs"
                      aria-label={`${title} ${index + 1}행 ${columns[column]?.title ?? ''}`}
                      value={row[column]}
                      onText={(text) =>
                        put(rows.map((one, at): Row => (at !== index ? one : column === 0 ? [cellOf(text), one[1]] : [one[0], cellOf(text)])))
                      }
                    />
                  </td>
                ))}
                <td className="text-center">
                  <button
                    type="button"
                    className="text-muted-foreground hover:text-destructive px-1"
                    aria-label={`${title} ${index + 1}행 삭제`}
                    onClick={() => put(rows.filter((_, at) => at !== index))}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <Textarea
          aria-label={`${title} 붙여넣기`}
          rows={3}
          className="font-mono text-xs"
          placeholder={`엑셀에서 두 열(${columns.map((one) => `${one.title}${one.unit ? ` ${one.unit}` : ''}`).join(', ')})을 복사해 붙여 넣으십시오.`}
          value={pasted}
          onChange={(event) => {
            setPasted(event.target.value)
            const got = pasteRows(event.target.value)
            if (got.length >= 2) {
              setPasted('')
              put(got)
            }
          }}
        />
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" size="sm" variant="outline" className="h-7 text-xs" onClick={() => put([...rows, ['', '']])}>
          행 추가
        </Button>
        {rows.length > 0 && (
          <Button type="button" size="sm" variant="ghost" className="h-7 text-xs" onClick={() => put([])}>
            모두 지우기
          </Button>
        )}
        {grms && rows.length > 0 && (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            title="IEC 60068-2-64처럼 PSD가 (m/s²)²/Hz로 적힌 표면 값을 9.80665² (≈ 96.17)로 나눠 g²/Hz로 바꿉니다."
            onClick={() => put(toG2(rows))}
          >
            (m/s²)²/Hz → g²/Hz
          </Button>
        )}
        {rows.length > 0 && <span className="text-muted-foreground text-xs">여러 행을 붙여 넣으면 표 전체가 바뀝니다.</span>}
        {shown !== null && (
          <span className="ml-auto text-xs font-medium" title="표를 로그-로그로 보간한 면적의 제곱근입니다. 규격의 Grms와 비교하십시오.">
            Grms {shown.toFixed(2)} g
          </span>
        )}
      </div>
      {description && <p className="text-muted-foreground text-xs">{description}</p>}
    </div>
  )
}
