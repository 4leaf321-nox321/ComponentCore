/**
 * **리본** — 조건 화면의 위 줄(`ConditionsPanel` 에서 나눴다, 동작 그대로). 도면 편집기와 같은 단추: 더하는 일은 여기서
 * 하고, 있는 것은 왼쪽 트리에서 보고 고친다. 「조건 저장」 도 여기 있다 — 격자 아래에 두면 3D 가 그만큼 작아진다.
 *
 * 무엇이 켜져 있는지(`state`)와 누르면 할 일(`on`)만 받는다 — 상태는 화면이 든다.
 */

import {
  Anchor,
  ArrowDownToLine,
  Axis3d,
  FlaskConical,
  Grid3x3,
  Group,
  Link2,
  Ruler,
  Save,
  ScanEye,
  Scissors,
  Settings2,
  Spline,
  TableProperties,
  Thermometer,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'

import { RibbonButton, RibbonGroup } from '@/modules/cad/Ribbon'

/** 리본 단추의 그림 — 조건 묶음마다 하나. */
const GROUP_ICONS: Record<string, LucideIcon> = {
  constraints: Anchor,
  loads: ArrowDownToLine,
  contacts: Link2,
  initial: Thermometer,
  mesh_hints: Grid3x3,
}

export interface RibbonState {
  /** 저장한 것과 다른가 — 「조건 저장」 이 눈에 띈다. */
  dirty: boolean
  saving?: boolean
  /** 조건 창이 열려 있나 — 저장을 막는다(창의 것이 아직 한 벌에 없다). */
  editing: boolean
  /** 열린 조건 창이 3D 선택을 받나 — 그러면 「선택 그룹」 창을 따로 열지 않는다. */
  editingTakesPicks: boolean
  grouping: boolean
  measuring: boolean
  showContacts: boolean
  section: boolean
  xray: boolean
  /** 바디 목록이 왔나 — 파트별 설정 표가 그것으로 그린다. */
  partsReady: boolean
}

export interface RibbonActions {
  onSave: () => void
  onToggleGrouping: () => void
  onPickMaterials: () => void
  onOpenParts: () => void
  onAdd: (group: string) => void
  /** 곡선을 더한다 — 없으면(옛 서버 — 사양표에 곡선이 없다) 단추도 없다. */
  onAddCurve?: () => void
  onAddFrame: () => void
  onToggleMeasuring: () => void
  onToggleContacts: () => void
  onToggleSection: () => void
  onToggleXray: () => void
  onOpenAnalysis: () => void
}

export function ConditionsRibbon({
  groups,
  state,
  on,
}: {
  /** 조건 묶음 — 「조건」 칸의 단추들(사양표의 이름). */
  groups: { key: string; label: string }[]
  state: RibbonState
  on: RibbonActions
}) {
  return (
    <div className="flex flex-wrap gap-2 rounded-md border p-2">
      <RibbonGroup title="저장">
        <RibbonButton
          icon={Save}
          label="조건 저장"
          title={state.editing ? '열려 있는 창을 먼저 확인하거나 취소하십시오.' : '도면은 변경되지 않으며, 새 버전이 생성되지 않습니다.'}
          active={state.dirty}
          disabled={state.saving || state.editing}
          onClick={on.onSave}
        />
      </RibbonGroup>
      <RibbonGroup title="선택">
        <RibbonButton
          icon={Group}
          label="선택 그룹"
          title={
            state.editingTakesPicks
              ? '조건 창이 열려 있는 동안 3D에서 선택한 형상은 해당 조건의 선택 그룹이 됩니다.'
              : '선택 그룹 추가: 3D에서 Ctrl 또는 Shift를 눌러 여러 형상을 선택합니다.'
          }
          active={state.grouping}
          disabled={state.editingTakesPicks}
          onClick={on.onToggleGrouping}
        />
      </RibbonGroup>
      <RibbonGroup title="파트">
        <RibbonButton icon={FlaskConical} label="물성" title="물성 추가: MatNexus에서 여러 물성을 함께 선택합니다." onClick={on.onPickMaterials} />
        <RibbonButton
          icon={TableProperties}
          label="파트별 설정"
          title="파트마다 물성, 거동(변형체·강체), 표현(솔리드·쉘), 해석 제외, 메시를 한 표에서 지정합니다."
          disabled={!state.partsReady}
          onClick={on.onOpenParts}
        />
      </RibbonGroup>
      <RibbonGroup title="조건">
        {groups.map((group) => (
          <RibbonButton
            key={group.key}
            icon={GROUP_ICONS[group.key] ?? Settings2}
            label={group.label}
            title={`${group.label} 추가`}
            onClick={() => on.onAdd(group.key)}
          />
        ))}
        {on.onAddCurve && (
          <RibbonButton
            icon={Spline}
            label="곡선"
            title="곡선 추가: 주파수에 따라 바뀌는 값(가속도 PSD · 주파수별 배율)을 이름 붙여 두고 여러 하중 · 케이스가 함께 가리킵니다."
            onClick={on.onAddCurve}
          />
        )}
      </RibbonGroup>
      <RibbonGroup title="좌표계·측정">
        <RibbonButton
          icon={Axis3d}
          label="좌표계"
          title="좌표계 추가: 조건의 x·y·z 방향을 정의합니다(원점·회전 또는 선택 그룹의 면 기준)."
          onClick={on.onAddFrame}
        />
        <RibbonButton
          icon={Ruler}
          label="측정"
          title="측정: 창을 연 상태에서 3D를 클릭합니다(측정 중에는 선택 그룹을 생성하지 않습니다)."
          active={state.measuring}
          onClick={on.onToggleMeasuring}
        />
      </RibbonGroup>
      <RibbonGroup title="보기">
        <RibbonButton
          icon={Link2}
          label="접촉 표시"
          title="접촉 표시: 정의된 접촉의 면을 3D에 표시합니다. 본딩(Tie)은 붉은색, 그 밖의 접촉(마찰 · 무마찰 · 분리 없음 · 거친)은 푸른색입니다."
          active={state.showContacts}
          onClick={on.onToggleContacts}
        />
        <RibbonButton
          icon={Scissors}
          label="단면"
          title="단면: X · Y · Z 축에 수직인 평면으로 모델을 잘라 내부를 표시합니다. 잘라 낸 쪽은 선택되지 않습니다."
          active={state.section}
          onClick={on.onToggleSection}
        />
        <RibbonButton
          icon={ScanEye}
          label="투명 보기"
          title="투명 보기: 모든 면을 반투명하게 하고, 접촉 · 선택 표시는 가려진 경우에도 앞에 표시합니다."
          active={state.xray}
          onClick={on.onToggleXray}
        />
      </RibbonGroup>
      <RibbonGroup title="해석">
        <RibbonButton icon={Settings2} label="해석 설정" onClick={on.onOpenAnalysis} />
      </RibbonGroup>
    </div>
  )
}
