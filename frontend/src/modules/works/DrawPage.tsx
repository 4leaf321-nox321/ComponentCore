/**
 * 그리기 — 새 작업의 시작. 템플릿에서 그리거나 STEP 을 올린다.
 *
 * 저장 전에는 아무것도 남지 않는다. 「내 작업으로 저장」 하면 작업이 생기고 그 화면으로 간다 —
 * 거기서 계속 고치고, 지그를 만들고, 부품 · 지그로 승격한다.
 */

import { useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { cadApi } from '@/modules/cad/api'
import type { Recipe } from '@/modules/cad/api'
import { RecipeEditor } from '@/modules/cad/RecipeEditor'
import { SaveTemplateDialog } from '@/modules/cad/SaveTemplateDialog'
import { worksApi } from '@/modules/works/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/shared/components/ui/select'
import { useResource } from '@/shared/hooks/useResource'

/** 템플릿 없이 — 피처를 하나씩 더해 처음부터 그린다. */
const EMPTY = '__empty__'

export default function DrawPage() {
  const navigate = useNavigate()
  const schema = useResource(() => cadApi.schema(), [])
  const saved = useResource(() => cadApi.templates(), [])
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [template, setTemplate] = useState(EMPTY)
  const [recipe, setRecipe] = useState<Recipe | null>({ version: 1, nodes: [] })
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)
  const fileInput = useRef<HTMLInputElement | null>(null)

  function pickTemplate(kind: string) {
    setTemplate(kind)
    if (kind === EMPTY) {
      setRecipe({ version: 1, nodes: [] })
      return
    }
    if (kind.startsWith('saved:')) {
      const found = saved.data?.find((t) => t.id === kind.slice(6))
      if (found) setRecipe(structuredClone(found.recipe))
      return
    }
    const next = schema.data?.templates[kind]
    if (next) setRecipe(structuredClone(next))
  }

  const pickedSaved = template.startsWith('saved:') ? saved.data?.find((t) => t.id === template.slice(6)) : undefined

  async function downloadStep() {
    if (!recipe) return
    setError(null)
    try {
      const blob = await cadApi.step(recipe)
      const href = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = href
      anchor.download = 'model.step'
      anchor.click()
      setTimeout(() => URL.revokeObjectURL(href), 10_000)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  async function save() {
    if (!recipe) return
    setBusy(true)
    setError(null)
    try {
      const made = await worksApi.create({
        name,
        recipe,
        source: template === EMPTY ? 'manual' : 'template',
        note: template === EMPTY ? '처음부터 그림' : `${template} 템플릿에서`,
      })
      navigate(`/works/${made.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  async function startFromStep(file: File) {
    setBusy(true)
    setError(null)
    try {
      const made = await worksApi.createFromStep(file)
      navigate(`/works/${made.id}`)
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  const header = (
    <div className="flex items-center gap-2">
      <Label className="text-xs">시작</Label>
      <Select value={template} onValueChange={pickTemplate}>
        <SelectTrigger className="w-56">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={EMPTY}>빈 레시피에서 — 처음부터 그리기</SelectItem>
          {Object.entries(schema.data?.template_labels ?? {}).map(([kind, label]) => (
            <SelectItem key={kind} value={kind}>
              기본: {label}
            </SelectItem>
          ))}
          {(saved.data ?? []).map((t) => (
            <SelectItem key={t.id} value={`saved:${t.id}`}>
              {t.mine ? '내 템플릿' : `공용 (${t.owner_name})`}: {t.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {pickedSaved?.mine && (
        <Button
          size="sm"
          variant="ghost"
          onClick={async () => {
            if (!window.confirm(`템플릿 「${pickedSaved.name}」 을 지웁니까? 시작 목록에서만 사라집니다.`)) return
            await cadApi.removeTemplate(pickedSaved.id)
            saved.reload()
            pickTemplate(EMPTY)
          }}
        >
          이 템플릿 지우기
        </Button>
      )}
      <span className="text-muted-foreground text-xs">
        {template === EMPTY ? '툴바의 「스케치」 를 눌러 놓고 「돌출」 하면 입체가 됩니다.' : '템플릿의 치수를 고쳐 쓰세요. 고르면 지금 것은 사라집니다.'}
      </span>
    </div>
  )

  return (
    <div className="space-y-4">
      <PageHeader
        title="그리기"
        description="템플릿에서 그리거나 STEP 을 올립니다. 「내 작업으로 저장」 하기 전에는 아무것도 남지 않습니다."
        actions={
          <>
            <input
              ref={fileInput}
              type="file"
              accept=".step,.stp"
              className="hidden"
              onChange={(event) => {
                const file = event.target.files?.[0]
                if (file) void startFromStep(file)
                event.target.value = ''
              }}
            />
            <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={busy}>
              {busy ? '올리는 중…' : 'STEP 파일에서 시작'}
            </Button>
          </>
        }
      />
      <ErrorNotice error={error ?? schema.error} />

      {recipe && (
        <RecipeEditor
          value={recipe}
          onChange={setRecipe}
          header={header}
          actions={
            <>
              <Button size="sm" variant="outline" onClick={() => void downloadStep()} disabled={recipe.nodes.length === 0}>
                STEP 받기
              </Button>
              <Button size="sm" variant="outline" onClick={() => setSavingTemplate(true)} disabled={recipe.nodes.length === 0}>
                템플릿으로 저장
              </Button>
              <Button size="sm" onClick={() => setSaving(true)} disabled={recipe.nodes.length === 0}>
                내 작업으로 저장
              </Button>
            </>
          }
        />
      )}

      {recipe && (
        <SaveTemplateDialog
          key={String(savingTemplate)}
          open={savingTemplate}
          recipe={recipe}
          defaultName={pickedSaved?.name}
          onClose={() => setSavingTemplate(false)}
          onSaved={() => saved.reload()}
        />
      )}

      <Dialog open={saving} onOpenChange={(open) => !open && !busy && setSaving(false)}>
        <DialogContent>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void save()
            }}
            className="space-y-4"
          >
            <DialogHeader>
              <DialogTitle>내 작업으로 저장</DialogTitle>
              <DialogDescription>내 공간에 작업이 생기고 버전 1 이 평가됩니다. 남에게는 승격해야 보입니다.</DialogDescription>
            </DialogHeader>
            <div className="space-y-2">
              <Label htmlFor="work-name">작업 이름</Label>
              <Input id="work-name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setSaving(false)} disabled={busy}>
                취소
              </Button>
              <Button type="submit" disabled={busy || !name.trim()}>
                {busy ? '저장 중…' : '저장'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
