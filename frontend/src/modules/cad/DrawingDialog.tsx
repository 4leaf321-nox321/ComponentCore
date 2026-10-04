/**
 * 도면 — 3각법 세 뷰(정면 · 평면 · 우측면)에 전체 치수 · 구멍 기호와 구멍표 · 표제란.
 *
 * 가공을 맡길 때 오가는 것은 아직 2D 도면이다. 표제란(이름 · 재료 · 메모)을 적고 미리 본 뒤
 * PDF(보내기) · DXF(CAD 에서 고치기 — 치수가 진짜 치수 객체) 로 받는다. 축척은 서버가 표준 축척
 * 중 들어가는 가장 큰 것으로 고르고, 치수 글씨는 늘 실제 크기다.
 */

import { useEffect, useState } from 'react'

import { cadApi } from '@/modules/cad/api'
import type { DrawingOptions, DrawingSummary, Recipe } from '@/modules/cad/api'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'

function save(blob: Blob, name: string) {
  const href = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = href
  anchor.download = name
  anchor.click()
  setTimeout(() => URL.revokeObjectURL(href), 10_000)
}

export function DrawingDialog({ open, recipe, defaultTitle = '', onClose }: { open: boolean; recipe: Recipe; defaultTitle?: string; onClose: () => void }) {
  const [options, setOptions] = useState<Required<DrawingOptions>>({ title: defaultTitle, sheet: 'A3', material: '', note: '' })
  const [preview, setPreview] = useState<string | null>(null)
  const [summary, setSummary] = useState<DrawingSummary | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [busy, setBusy] = useState(false)

  // 표제란을 고치면 잠깐 기다렸다 다시 그린다 — 한 글자마다 그리면 서버가 바쁘다.
  useEffect(() => {
    if (!open) return
    let alive = true
    let made: string | null = null
    const timer = setTimeout(() => {
      Promise.all([cadApi.drawing(recipe, 'svg', options), cadApi.drawingSummary(recipe, options)])
        .then(([blob, info]) => {
          if (!alive) return
          made = URL.createObjectURL(blob)
          setPreview(made)
          setSummary(info)
          setError(null)
        })
        .catch((caught) => alive && setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.')))
    }, 400)
    return () => {
      alive = false
      clearTimeout(timer)
      if (made) URL.revokeObjectURL(made)
    }
  }, [open, recipe, options])

  async function download(format: 'pdf' | 'dxf') {
    setBusy(true)
    setError(null)
    try {
      save(await cadApi.drawing(recipe, format, options), `${options.title || '도면'}.${format}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류가 발생했습니다.'))
    } finally {
      setBusy(false)
    }
  }

  const set = (patch: Partial<DrawingOptions>) => setOptions((now) => ({ ...now, ...patch }))
  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-5xl">
        <DialogHeader>
          <DialogTitle>도면</DialogTitle>
          <DialogDescription>3각법 3면도, 전체 치수, 구멍표, 표제란으로 구성됩니다. 구멍 위치는 해당 구멍이 원으로 보이는 뷰의 왼쪽 아래 모서리를 기준으로 측정합니다.</DialogDescription>
        </DialogHeader>
        <div className="grid gap-2 sm:grid-cols-[2fr_1fr_auto_2fr]">
          <Input aria-label="도면 이름" placeholder="이름" value={options.title} onChange={(e) => set({ title: e.target.value })} />
          <Input aria-label="재료" placeholder="재료 (예: SS400)" value={options.material} onChange={(e) => set({ material: e.target.value })} />
          <select aria-label="용지" className="bg-background h-9 rounded-md border px-2 text-sm" value={options.sheet} onChange={(e) => set({ sheet: e.target.value as 'A3' | 'A4' })}>
            <option value="A3">A3</option>
            <option value="A4">A4</option>
          </select>
          <Input aria-label="메모" placeholder="메모 (공차, 다듬질)" value={options.note} onChange={(e) => set({ note: e.target.value })} />
        </div>
        <div className="bg-muted/30 flex min-h-64 items-center justify-center rounded-md border">
          {preview ? <img src={preview} alt="도면 미리보기" className="max-h-[60vh] w-full object-contain" /> : <span className="text-muted-foreground text-sm">생성 중…</span>}
        </div>
        {summary && (
          <p className="text-muted-foreground text-xs">
            {summary.sheet} · 축척 {summary.scale} · 구멍 {summary.holes.length} 개{summary.notes.length > 0 && ` · ${summary.notes.join(' · ')}`}
          </p>
        )}
        <ErrorNotice error={error} />
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose}>
            닫기
          </Button>
          <Button variant="outline" disabled={busy || !summary} onClick={() => void download('dxf')}>
            DXF 다운로드
          </Button>
          <Button disabled={busy || !summary} onClick={() => void download('pdf')}>
            PDF 다운로드
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
