/**
 * 그리기 — 새 작업의 시작. 템플릿에서 그리거나 STEP 을 올린다.
 *
 * 저장 전에는 아무것도 남지 않는다. 「내 작업으로 저장」 하면 작업이 생기고 그 화면으로 간다 —
 * 거기서 계속 고치고, 지그를 만들고, 부품 · 지그로 승격한다.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'

import type { Recipe } from '@/modules/cad/api'
import { saveRecipeAs } from '@/modules/cad/download'
import { templatesApi } from '@/modules/templates/api'
import { RecipeEditor } from '@/modules/cad/RecipeEditor'
import { SaveTemplateDialog } from '@/modules/templates/SaveTemplateDialog'
import { worksApi } from '@/modules/works/api'
import { ApiError } from '@/shared/api/client'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { Button } from '@/shared/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'

/** 어디서 왔는지 — 저장할 때 버전 메모가 된다. */
type Origin = { source: 'manual' | 'template' | 'copy'; label: string }

export default function DrawPage() {
  const navigate = useNavigate()
  const [savingTemplate, setSavingTemplate] = useState(false)
  const [origin, setOrigin] = useState<Origin>({
    source: 'manual',
    label: '처음부터 그림',
  })
  const [recipe, setRecipe] = useState<Recipe | null>({
    version: 1,
    nodes: [],
  })
  const [saving, setSaving] = useState(false)
  const [name, setName] = useState('')
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)
  const fileInput = useRef<HTMLInputElement | null>(null)
  const [params, setParams] = useSearchParams()

  // 템플릿 공간에서 「그리기에서 열기」 로 왔을 때 — 주소의 id 를 받아 한 번만 싣는다.
  const wanted = params.get('template')
  useEffect(() => {
    if (!wanted) return
    let alive = true
    void (async () => {
      try {
        const template = await templatesApi.get(wanted)
        if (!alive) return
        setRecipe(template.recipe)
        setName(template.name)
        setOrigin({ source: 'template', label: `${template.name} 템플릿에서` })
      } catch (caught) {
        if (alive) setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
      } finally {
        // 주소를 비워 둔다 — 새로고침이나 「새로」 뒤에 다시 실리면 사람이 놀란다.
        if (alive) setParams({}, { replace: true })
      }
    })()
    return () => {
      alive = false
    }
  }, [wanted, setParams])

  async function download(format: 'step' | 'stl' | 'dxf' | 'svg') {
    if (!recipe) return
    setError(null)
    try {
      await saveRecipeAs(recipe, format, name || 'model')
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
        source: origin.source,
        note: origin.label,
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

  return (
    <div className="space-y-4">
      <PageHeader
        title="그리기"
        description="빈 화면에서 그리거나 「파일」 탭에서 템플릿 · 기존 작업을 불러옵니다. 저장하기 전에는 아무것도 남지 않습니다."
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
      <ErrorNotice error={error} />

      {recipe && (
        <RecipeEditor
          value={recipe}
          onChange={setRecipe}
          file={{
            save: { label: '내 작업으로', run: () => setSaving(true) },
            saveTemplate: () => setSavingTemplate(true),
            download: (format) => void download(format),
            onLoaded: (label, source) => setOrigin(source === 'copy' ? { source, label: `${label} 에서 복사` } : { source, label: `${label} 템플릿에서` }),
          }}
        />
      )}

      {recipe && <SaveTemplateDialog key={String(savingTemplate)} open={savingTemplate} recipe={recipe} onClose={() => setSavingTemplate(false)} />}

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
