import type { Recipe } from "@/modules/cad/api";
import type { Job } from "@/modules/jobs/api";
import { api } from "@/shared/api/client";
import type { Page } from "@/shared/api/types";
import type { MeshData } from "@/shared/viewer/PickViewer";

/** 인자 하나 — 고정이거나, 구간이거나, 값 목록. */
export interface Factor {
  name: string;
  mode: "fixed" | "range" | "list";
  value?: number | null;
  start?: number | null;
  end?: number | null;
  /** 칸을 비우면 null — 다 지우고 처음부터 칠 수 있어야 한다. 비어 있으면 만들기가 막힌다. */
  steps?: number | null;
  values?: number[];
  /** 값을 맞추는 가공 단위(mm). 없으면 0.1 — 0.333 같은 치수는 가공할 수 없다. */
  resolution?: number | null;
}

export interface DoePoint {
  id: string;
  number: number;
  params: Record<string, number>;
  status: "pending" | "ok" | "failed";
  error: string;
  /** 해석 결과가 붙을 자리 — 붙이는 길이 아직 없어 지금은 늘 null. */
  metrics: Record<string, number | null> | null;
  /** 조립이면 구성품끼리 겹침(ok · items · total_volume). 구성품이 하나면 null. */
  interference: {
    ok: boolean;
    total_volume: number;
    items: { a: string; b: string; volume: number; ok: boolean }[];
  } | null;
  step_file: string;
}

export interface DoeStudySummary {
  id: string;
  name: string;
  description: string;
  work_id: string | null;
  work_name: string | null;
  work_kind: "part" | "jig" | "assembly" | null;
  method: "factorial" | "lhs";
  samples: number;
  seed: number;
  point_count: number;
  created_at: string;
}

export interface DoeStudy extends DoeStudySummary {
  recipe: Recipe;
  factors: Factor[];
  /**
   * 서버 보관 폴더에 설계점 파일이 **아직 있나.** 보관 기한이 지나 치워졌으면 false —
   * 그러면 CSV 는 되지만(DB 에서 그린다) 「보내기」 는 막힌다. 「다시 만들기」 가 되살린다.
   */
  local_ready: boolean;
  /** 해석 쪽이 여는 경로(F:\…). 서버가 보는 경로는 안 내려온다. */
  export_dir_windows: string;
  /** 마지막으로 공유 폴더에 보낸 때. 없으면 아직 서버 안에만 있다. */
  exported_at: string | null;
  job: Job | null;
  points: DoePoint[];
  done: number;
  failed: number;
}

/** 설계점 하나의 형상 — 스냅샷 레시피에 그 점의 값을 넣어 다시 만든 것. */
export interface PointMesh {
  number: number;
  params: Record<string, number>;
  summary: { bbox: { size: number[] } } & Record<string, unknown>;
  mesh: MeshData;
}

export interface Preview {
  count: number;
  max: number;
  /** LHS 표본 수 상한 — 관리자 설정. */
  max_samples: number;
  too_many: boolean;
  points: Record<string, number>[];
  varying: string[];
}

export const doeApi = {
  preview: (body: {
    factors: Factor[];
    method?: string;
    samples?: number;
    seed?: number;
  }) => api.post<Preview>("/doe/preview", body),
  list: (
    options: { workId?: string; offset?: number; limit?: number } = {},
  ) => {
    const query = new URLSearchParams({
      offset: String(options.offset ?? 0),
      limit: String(options.limit ?? 50),
    });
    if (options.workId) query.set("work_id", options.workId);
    return api.get<Page<DoeStudySummary>>(`/doe?${query}`);
  },
  get: (id: string) => api.get<DoeStudy>(`/doe/${id}`),
  create: (body: {
    name: string;
    description?: string;
    recipe: Recipe;
    factors: Factor[];
    method?: string;
    samples?: number;
    seed?: number;
    work_id?: string | null;
  }) => api.post<DoeStudy>("/doe", body),
  /** 설계점 하나의 형상 — 화면이 점마다 3D 로 본다. */
  pointMesh: (id: string, number: number) =>
    api.get<PointMesh>(`/doe/${id}/points/${number}/mesh`),
  /** 서버 보관 폴더의 STEP · 표를 공유 폴더로 — 해석은 그때부터 읽는다. 다시 누르면 덮어쓴다. */
  export: (id: string) => api.post<DoeStudy>(`/doe/${id}/export`),
  /**
   * **다시 만들기** — 스냅샷(레시피 · 인자 · 시드 · 조건)으로 설계점 파일을 되살린다.
   * 같은 스터디에 같은 것이 다시 난다. `only='failed'` 면 실패한 점만.
   */
  rerun: (id: string, only: "all" | "failed" = "all") =>
    api.post<DoeStudy>(`/doe/${id}/rerun?only=${only}`),
  remove: (id: string) => api.delete<void>(`/doe/${id}`),
  manifestUrl: (id: string) => `/api/doe/${id}/manifest.csv`,
};
