/**
 * 내 작업 하나.
 *
 * **부품이든 지그든 그리는 방법은 같다** — 도면 한 줄기다. 다른 것은 작업의 **종류**뿐이고,
 * 그것이 「탭」 과 「어디로 승격하나」 와 「덤으로 무엇을 쓸 수 있나」 를 정한다:
 *
 * - 부품: 탭 = 도면 · 실험계획, 승격 = **공용 부품**, 덤 = 지그 생성기(이 부품을 잡는 지그를
 *   규칙으로 만들어 준다).
 * - 지그: 탭 = 도면 · 실험계획, 승격 = **공용 지그**.
 * - 조립: 탭 = 조립 · 실험계획. 부품 · 지그를 가져다 놓는다(승격은 없다).
 *
 * 그래서 「이 도면을 무엇으로 올릴까」 를 물을 일이 없다 — 종류가 이미 답이다.
 */

import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'

import type { Recipe } from '@/modules/cad/api'
import { WorkDoeTab } from '@/modules/doe/WorkDoeTab'
import { AssemblyEditor } from '@/modules/works/AssemblyEditor'
import { GeometryJobView } from '@/modules/cad/GeometryJobView'
import { RecipeEditor } from '@/modules/cad/RecipeEditor'
import { saveRecipeAs } from '@/modules/cad/download'
import { SaveTemplateDialog } from '@/modules/templates/SaveTemplateDialog'
import { JigResultView } from '@/modules/jigs/JigResultView'
import type { Job } from '@/modules/jobs/api'
import { worksApi } from '@/modules/works/api'
import type { WorkVersion } from '@/modules/works/api'
import { JigOptionsForm } from '@/modules/works/JigOptionsForm'
import { ApiError } from '@/shared/api/client'
import { ConfirmDialog } from '@/shared/components/ConfirmDialog'
import { EmptyState } from '@/shared/components/EmptyState'
import { ErrorNotice } from '@/shared/components/ErrorNotice'
import { PageHeader } from '@/shared/components/PageHeader'
import { StatusBadge } from '@/shared/components/StatusBadge'
import { Button } from '@/shared/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/shared/components/ui/card'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/shared/components/ui/dialog'
import { Input } from '@/shared/components/ui/input'
import { Label } from '@/shared/components/ui/label'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/shared/components/ui/tabs'
import { useResource } from '@/shared/hooks/useResource'
import { shownDateTime } from '@/shared/lib/datetime'

const SOURCE_LABELS: Record<string, string> = {
  template: '템플릿',
  manual: '직접',
  ai: 'AI',
  import: 'STEP',
  restore: '되돌림',
  copy: '복사',
}

export default function WorkPage() {
  const { id = '' } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const work = useResource(() => worksApi.get(id), [id])
  const versions = useResource(() => worksApi.versions(id), [id])
  const runs = useResource(() => worksApi.jigRuns(id), [id])
  const defaults = useResource(() => worksApi.jigOptions(), [])

  const [tab, setTab] = useState('geometry')
  const [selectedVersion, setSelectedVersion] = useState<WorkVersion | null>(null)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<Recipe | null>(null)
  const [note, setNote] = useState('')
  const [options, setOptions] = useState<Record<string, unknown> | null>(null)
  const [selectedRun, setSelectedRun] = useState<Job | null>(null)
  const [promoting, setPromoting] = useState<'part' | 'jig' | 'jig-recipe' | null>(null)
  const [promoteName, setPromoteName] = useState('')
  const [promoteNote, setPromoteNote] = useState('')
  const [promoteProduct, setPromoteProduct] = useState(true)
  const [deleting, setDeleting] = useState(false)
  const [savingTemplate, setSavingTemplate] = useState(false)
  /** 생성기 옵션은 접어 둔다 — 서른 개를 펼쳐 두면 무엇을 해야 할지 안 보인다. */
  const [showOptions, setShowOptions] = useState(false)
  const [error, setError] = useState<ApiError | Error | null>(null)
  const [busy, setBusy] = useState(false)
  const fileInput = useRef<HTMLInputElement | null>(null)

  const w = work.data

  useEffect(() => {
    if (!selectedVersion && w?.current) setSelectedVersion(w.current)
  }, [w, selectedVersion])
  useEffect(() => {
    if (!selectedRun && runs.data && runs.data.length > 0) setSelectedRun(runs.data[0])
  }, [runs.data, selectedRun])
  useEffect(() => {
    if (options || !w || !defaults.data) return
    const saved = Object.keys(w.jig_options).length > 0 ? w.jig_options : defaults.data
    setOptions({ ...defaults.data, ...saved })
  }, [w, defaults.data, options])

  function reloadAll() {
    work.reload()
    versions.reload()
    runs.reload()
  }

  async function act(fn: () => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      await fn()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    } finally {
      setBusy(false)
    }
  }

  function startEditing() {
    setDraft(structuredClone(selectedVersion?.recipe ?? w?.current?.recipe ?? null))
    setEditing(true)
  }

  async function downloadDraft(format: 'step' | 'stl' | 'dxf' | 'svg') {
    if (!draft) return
    setError(null)
    try {
      await saveRecipeAs(draft, format, w?.name ?? 'model')
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error('알 수 없는 오류'))
    }
  }

  async function saveVersion() {
    if (!draft) return
    await act(async () => {
      const made = await worksApi.addVersion(id, {
        recipe: draft,
        source: 'manual',
        note,
      })
      setEditing(false)
      setNote('')
      setSelectedVersion(made)
      reloadAll()
    })
  }

  async function runJig() {
    await act(async () => {
      const made = await worksApi.runJig(id, options ?? {})
      setSelectedRun(made)
      setTab('jig')
      runs.reload()
    })
  }

  async function promote() {
    await act(async () => {
      if (promoting === 'part') {
        const made = await worksApi.promotePart(id, {
          name: promoteName || undefined,
          note: promoteNote,
        })
        setPromoting(null)
        reloadAll()
        navigate(`/parts/${made.part_id}`)
      } else if (promoting === 'jig-recipe') {
        const made = await worksApi.promoteJigRecipe(id, {
          name: promoteName || undefined,
          note: promoteNote,
        })
        setPromoting(null)
        reloadAll()
        navigate(`/jigs/${made.jig_id}`)
      } else if (promoting === 'jig' && selectedRun) {
        const made = await worksApi.promoteJig(id, {
          job_id: selectedRun.id,
          name: promoteName || undefined,
          note: promoteNote,
          promote_product: promoteProduct,
        })
        setPromoting(null)
        reloadAll()
        navigate(`/jigs/${made.jig_id}`)
      }
    })
  }

  if (work.error) return <ErrorNotice error={work.error} />
  if (!w) return null

  /** 이 작업이 만드는 것 — 화면의 말과 갈 곳이 여기서 갈린다. */
  const isJig = w.kind === 'jig'
  const isAssembly = w.kind === 'assembly'

  const currentPromoted = w.current?.promoted_part_id != null

  return (
    <div className="space-y-4">
      <PageHeader
        title={w.name}
        description={w.description || `v${w.current_version} · ${shownDateTime(w.updated_at)}`}
        back={{ to: '/works', label: '내 작업' }}
        actions={
          <>
            {w.promoted_part_id && (
              <Link to={`/parts/${w.promoted_part_id}`} className="text-muted-foreground text-xs hover:underline">
                부품으로 올라감
              </Link>
            )}
            {w.promoted_jig_id && (
              <Link to={`/jigs/${w.promoted_jig_id}`} className="text-muted-foreground text-xs hover:underline">
                지그로 올라감
              </Link>
            )}
            <Button variant="ghost" onClick={() => setDeleting(true)} disabled={busy}>
              지우기
            </Button>
          </>
        }
      />
      <ErrorNotice error={error} />

      <Tabs value={tab} onValueChange={setTab}>
        <TabsList>
          <TabsTrigger value="geometry">
            {isAssembly ? '조립' : '도면'} {w.current_version > 0 && `v${w.current_version}`}
          </TabsTrigger>
          {/* 지그 생성기는 **부품 도면의 덤**이다 — 지그 · 조립 작업에는 나오지 않는다. */}
          {!isJig && !isAssembly && (
            <TabsTrigger value="jig">지그 만들어 주기 {w.jig_run_count > 0 && `(${w.jig_run_count})`}</TabsTrigger>
          )}
          <TabsTrigger value="doe">실험계획</TabsTrigger>
        </TabsList>

        {/* ---------------- 부품 ---------------- */}
        <TabsContent value="geometry" className="space-y-4 pt-4">
          {editing && draft ? (
            <Card>
              <CardHeader>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>새 버전 (v{w.current_version + 1})</CardTitle>
                  <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder="무엇을 바꿨나" className="h-8 w-56" />
                  <span className="text-muted-foreground text-xs">저장은 「파일」 탭에서.</span>
                  <Button size="sm" variant="ghost" className="ml-auto" onClick={() => setEditing(false)} disabled={busy}>
                    고치기 취소
                  </Button>
                </div>
              </CardHeader>
              <CardContent>
                {isAssembly ? (
                  <AssemblyEditor value={draft} onChange={setDraft} />
                ) : (
                <RecipeEditor
                  value={draft}
                  onChange={setDraft}
                  file={{
                    save: {
                      label: '새 버전으로',
                      run: () => void saveVersion(),
                      disabled: busy,
                    },
                    saveTemplate: () => setSavingTemplate(true),
                    download: (format) => void downloadDraft(format),
                    onLoaded: (label, source) => setNote(source === 'copy' ? `${label} 에서 복사` : `${label} 템플릿에서`),
                    currentWorkId: id,
                  }}
                />
                )}
                {isAssembly && (
                  <div className="mt-3 flex items-center gap-2">
                    <Button size="sm" onClick={() => void saveVersion()} disabled={busy}>
                      새 버전으로 저장
                    </Button>
                    <span className="text-muted-foreground text-xs">저장해야 3D 와 실험계획에 반영됩니다.</span>
                  </div>
                )}
              </CardContent>
            </Card>
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={startEditing} disabled={busy || w.current_version === 0}>
                  수정
                </Button>
                <input
                  ref={fileInput}
                  type="file"
                  accept=".step,.stp"
                  className="hidden"
                  onChange={(event) => {
                    const file = event.target.files?.[0]
                    if (file)
                      void act(async () => {
                        const made = await worksApi.importStep(id, file)
                        setSelectedVersion(made)
                        reloadAll()
                      })
                    event.target.value = ''
                  }}
                />
                <Button variant="outline" onClick={() => fileInput.current?.click()} disabled={busy}>
                  STEP 올리기
                </Button>
                <Button variant="outline" onClick={() => setSavingTemplate(true)} disabled={busy || !selectedVersion}>
                  템플릿으로 저장
                  {selectedVersion && selectedVersion.number !== w.current_version ? ` (v${selectedVersion.number})` : ''}
                </Button>
                <div className="flex-1" />
                {!isAssembly && (
                <Button
                  variant="outline"
                  disabled={busy || w.current_version === 0 || (!isJig && currentPromoted)}
                  onClick={() => {
                    setPromoteName(w.name)
                    setPromoteNote('')
                    setPromoting(isJig ? 'jig-recipe' : 'part')
                  }}
                  title={
                    isJig
                      ? '이 지그 그림을 지그 카탈로그에 올립니다'
                      : currentPromoted
                        ? '현재 버전은 이미 부품에 올라가 있습니다'
                        : undefined
                  }
                >
                  {isJig
                    ? '공용 지그로 승격'
                    : currentPromoted
                      ? `부품 v${w.current?.promoted_part_version} 으로 올라감`
                      : '공용 부품으로 승격'}
                </Button>
                )}
              </div>

              {w.current_version === 0 && isAssembly ? (
                <EmptyState
                  title="빈 조립입니다"
                  hint="「구성품 놓기」 를 누르면 왼쪽 라이브러리에서 부품 · 지그를 가져와 놓을 수 있습니다."
                  action={
                    <Button
                      onClick={() => {
                        setDraft({ version: 1, nodes: [] })
                        setEditing(true)
                      }}
                    >
                      구성품 놓기
                    </Button>
                  }
                />
              ) : w.current_version === 0 ? (
                <EmptyState
                  title="부품이 없습니다"
                  hint="이 작업은 옛 지그 프로젝트에서 옮겨 와 부품이 없습니다. STEP 을 올리거나 새로 그리세요."
                  action={<Button onClick={() => navigate('/draw')}>그리러 가기</Button>}
                />
              ) : (
                <div className="grid gap-4 lg:grid-cols-4">
                  <Card className="lg:col-span-1">
                    <CardHeader>
                      <CardTitle>버전</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ul className="space-y-1">
                        {(versions.data ?? []).map((one) => (
                          <li key={one.id}>
                            <button
                              type="button"
                              onClick={() => setSelectedVersion(one)}
                              className={`w-full rounded-md px-2 py-1.5 text-left text-sm ${selectedVersion?.id === one.id ? 'bg-accent' : 'hover:bg-accent/60'}`}
                            >
                              <div className="flex items-center justify-between">
                                <span className="font-medium">
                                  v{one.number}
                                  {one.number === w.current_version && <span className="text-muted-foreground ml-1 text-xs">현재</span>}
                                  {one.promoted_part_id && <span className="ml-1 rounded border px-1 text-[10px]">부품 v{one.promoted_part_version}</span>}
                                </span>
                                {one.job && <StatusBadge kind="run" value={one.job.status} />}
                              </div>
                              <p className="text-muted-foreground truncate text-xs">
                                {SOURCE_LABELS[one.source] ?? one.source} · {one.note || '—'}
                              </p>
                              <p className="text-muted-foreground text-xs">{shownDateTime(one.created_at)}</p>
                            </button>
                            {one.number !== w.current_version && (
                              <Button
                                size="sm"
                                variant="ghost"
                                className="h-6 px-2 text-xs"
                                disabled={busy}
                                onClick={() =>
                                  act(async () => {
                                    const made = await worksApi.restore(id, one.number)
                                    setSelectedVersion(made)
                                    reloadAll()
                                  })
                                }
                              >
                                이 버전으로 되돌리기
                              </Button>
                            )}
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                  <div className="lg:col-span-3">
                    {selectedVersion && (
                      <GeometryJobView
                        key={selectedVersion.id}
                        job={selectedVersion.job}
                        title={`v${selectedVersion.number}`}
                        stepName={`${w.name}-v${selectedVersion.number}.step`}
                        onFinished={reloadAll}
                      />
                    )}
                  </div>
                </div>
              )}
            </>
          )}
        </TabsContent>

        {/* ---------------- 지그 ---------------- */}
        <TabsContent value="jig" className="space-y-4 pt-4">
          {isJig || isAssembly ? null : (
          <Card>
            <CardHeader>
              <CardTitle>지그 생성기</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* **무엇을 해 주는지 한 줄로.** 옵션 서른 개를 먼저 보여 주면 아무도 안 누른다. */}
              <p className="text-muted-foreground text-sm">
                이 부품(v{w.current_version})을 올려놓고 잡는 지그를 규칙으로 만들어 줍니다 — <b>바닥판 · 받침 · 위치 핀 · 클램프</b>를 놓고 간섭을 검사합니다. 기본값 그대로 눌러 보고, 결과를 보며 고치면 됩니다.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Button onClick={() => void runJig()} disabled={busy || !options || w.current_version === 0}>
                  {busy ? '거는 중…' : '지그 만들어 보기'}
                </Button>
                <Button variant="outline" size="sm" onClick={() => setShowOptions(!showOptions)}>
                  {showOptions ? '세부 옵션 접기' : '세부 옵션 펴기'}
                </Button>
                {showOptions && (
                  <Button variant="ghost" size="sm" onClick={() => defaults.data && setOptions(defaults.data)}>
                    기본값으로
                  </Button>
                )}
                {w.current_version === 0 && <span className="text-muted-foreground text-xs">부품이 있어야 지그를 만들 수 있습니다.</span>}
              </div>
              {showOptions && options && <JigOptionsForm values={options} onChange={setOptions} />}
            </CardContent>
          </Card>
          )}

          {!isJig && (
          <div className="grid gap-4 lg:grid-cols-4">
            <Card className="lg:col-span-1">
              <CardHeader>
                <CardTitle>실행 기록</CardTitle>
              </CardHeader>
              <CardContent>
                {(runs.data ?? []).length === 0 ? (
                  <p className="text-muted-foreground text-sm">아직 만든 지그가 없습니다.</p>
                ) : (
                  <ul className="space-y-1">
                    {(runs.data ?? []).map((one) => (
                      <li key={one.id}>
                        <button
                          type="button"
                          onClick={() => setSelectedRun(one)}
                          className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-left text-sm ${
                            selectedRun?.id === one.id ? 'bg-accent' : 'hover:bg-accent/60'
                          }`}
                        >
                          <span>{shownDateTime(one.created_at)}</span>
                          <StatusBadge kind="run" value={one.status} />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <div className="lg:col-span-3">
              {selectedRun ? (
                <JigResultView
                  key={selectedRun.id}
                  job={selectedRun}
                  onFinished={() => {
                    runs.reload()
                    work.reload()
                  }}
                  actions={
                    selectedRun.status === 'done' && (
                      <>
                        {/* 생성기는 **출발점**이다 — 이어서 그리려면 지그 작업으로 가져간다. */}
                        <Button
                          size="sm"
                          variant="outline"
                          disabled={busy}
                          title="결과를 지그 작업으로 가져옵니다 — 거기서 고치고 변수 · 실험계획을 씁니다"
                          onClick={() =>
                            void act(async () => {
                              const made = await worksApi.jigRunToWork(id, selectedRun.id)
                              navigate(`/works/${made.id}`)
                            })
                          }
                        >
                          이어서 그리기 (지그 작업으로)
                        </Button>
                        <Button
                          size="sm"
                          onClick={() => {
                            setPromoteName(`${w.name} 지그`)
                            setPromoteNote('')
                            setPromoteProduct(true)
                            setPromoting('jig')
                          }}
                          disabled={busy}
                        >
                          공용 지그로 승격
                        </Button>
                      </>
                    )
                  }
                />
              ) : (
                <EmptyState title="아직 만든 지그가 없습니다" hint="위의 「지그 만들어 보기」 를 누르면 여기에 3D 와 배치 계획이 뜹니다. 기본값으로 한 번 만들어 보고 고치는 편이 빠릅니다." />
              )}
            </div>
          </div>
          )}
        </TabsContent>

        {/* ---------------- 실험계획 ---------------- */}
        <TabsContent value="doe" className="space-y-4 pt-4">
          <WorkDoeTab
            workId={id}
            work={w}
            // 저장하지 않은 고침이 있으면 DOE 는 그것을 못 본다 — 탭이 그 사실을 말하게 한다.
            pendingDraft={editing && draft !== null && JSON.stringify(draft) !== JSON.stringify(w.current?.recipe)}
            onEditRecipe={() => {
              setTab('geometry')
              // 이미 고치는 중이면 **다시 시작하지 않는다** — 적어 둔 것이 날아간다.
              if (!editing) startEditing()
            }}
          />
        </TabsContent>
      </Tabs>

      <Dialog open={promoting !== null} onOpenChange={(open) => !open && !busy && setPromoting(null)}>
        <DialogContent>
          <form
            onSubmit={(event) => {
              event.preventDefault()
              void promote()
            }}
            className="space-y-4"
          >
            <DialogHeader>
              <DialogTitle>{promoting === 'part' ? '공용 부품으로 승격' : '공용 지그로 승격'}</DialogTitle>
              <DialogDescription>
                {promoting === 'part'
                  ? `부품 v${w.current_version} 이 **공용 부품**으로 올라갑니다. 올라간 버전은 바뀌지 않습니다 — 고치려면 여기서 고쳐 다시 승격합니다.`
                  : promoting === 'jig-recipe'
                    ? `지금 도면(v${w.current_version})을 **공용 지그**로 올립니다. 생성기를 거치지 않으므로 계획 · 간섭 검사는 없고, 형상과 STEP 만 올라갑니다.`
                    : '이 지그 생성 결과가 공용 지그로 올라갑니다. 어느 부품 버전의 지그인지 함께 고정됩니다.'}
              </DialogDescription>
            </DialogHeader>
            {!(promoting === 'part' ? w.promoted_part_id : promoting === 'jig' ? w.promoted_jig_id : false) && (
              <div className="space-y-2">
                <Label htmlFor="promote-name">카탈로그 이름</Label>
                <Input id="promote-name" value={promoteName} onChange={(e) => setPromoteName(e.target.value)} />
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="promote-note">메모</Label>
              <Input id="promote-note" value={promoteNote} onChange={(e) => setPromoteNote(e.target.value)} placeholder="무엇이 바뀌었나" />
            </div>
            {promoting === 'jig' && !currentPromoted && (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={promoteProduct} onChange={(e) => setPromoteProduct(e.target.checked)} />
                제품(부품 v{w.current_version})도 카탈로그에 함께 올린다
              </label>
            )}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setPromoting(null)} disabled={busy}>
                취소
              </Button>
              <Button type="submit" disabled={busy}>
                {busy ? '올리는 중…' : '승격'}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {selectedVersion && (
        <SaveTemplateDialog
          key={String(savingTemplate)}
          open={savingTemplate}
          recipe={editing && draft ? draft : selectedVersion.recipe}
          defaultName={w.name}
          onClose={() => setSavingTemplate(false)}
        />
      )}

      <ConfirmDialog
        open={deleting}
        title="작업을 지웁니다"
        description={`「${w.name}」 이 내 작업에서 사라집니다. 이미 승격한 부품 · 지그는 남습니다.`}
        confirmLabel="지우기"
        destructive
        onConfirm={async () => {
          await worksApi.remove(id)
          navigate('/works')
        }}
        onClose={() => setDeleting(false)}
      />
    </div>
  )
}
