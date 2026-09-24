/**
 * **다시 만들기** — 파일이 치워져도 이력이 뜻을 갖게 하는 길.
 *
 * 설계점 파일은 보관 기한이 지나면 치워지지만 스냅샷(레시피 · 인자 · 시드 · 조건)은 DB 에
 * 남는다. 화면이 해야 할 일은 그 사정과 **할 일**을 한자리에서 말하는 것이다 — 「보내기」 가
 * 왜 안 눌리는지 모른 채로 두면 사람은 스터디를 다시 만든다.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { DoeStudy } from "@/modules/doe/api";
import { DoeStudyView } from "@/modules/doe/DoeStudyView";

vi.mock("@/shared/viewer/PickViewer", () => ({
  default: () => <div data-testid="viewer" />,
}));
vi.mock("@/shared/viewer/GridViewer", () => ({
  GridViewer: () => <div data-testid="grid" />,
}));

const study = (over: Partial<DoeStudy>) =>
  ({
    id: "s1",
    name: "두께 훑기",
    method: "factorial",
    seed: 1,
    point_count: 2,
    done: 2,
    failed: 0,
    local_ready: true,
    job: { status: "done", artifacts: [], progress: [] },
    export_dir_windows: "",
    exported_at: null,
    factors: [{ name: "두께", mode: "list", values: [2, 4] }],
    points: [
      {
        id: "a",
        number: 1,
        params: { 두께: 2 },
        status: "ok",
        error: "",
        step_file: "points/p0001.step",
      },
      {
        id: "b",
        number: 2,
        params: { 두께: 4 },
        status: "ok",
        error: "",
        step_file: "points/p0002.step",
      },
    ],
    ...over,
  }) as unknown as DoeStudy;

function mockFetch(seen: string[]) {
  vi.spyOn(globalThis, "fetch").mockImplementation(async (input, init) => {
    const url = String(input);
    seen.push(`${(init?.method ?? "GET").toUpperCase()} ${url}`);
    const body = url.includes("/server/display")
      ? { doe_gallery_max: 24, list_page_size: 20 }
      : {};
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  });
}

test("파일이 치워졌으면 사정과 할 일을 말하고, 「보내기」 는 막는다", async () => {
  const seen: string[] = [];
  mockFetch(seen);
  const reload = vi.fn();
  render(
    <MemoryRouter>
      <DoeStudyView study={study({ local_ready: false })} onReload={reload} />
    </MemoryRouter>,
  );

  expect(
    screen.getByText(/보관 기한을 지나 정리되었습니다/),
  ).toBeInTheDocument();
  // **설정은 남아 있다** — 사람이 스터디를 다시 만들지 않게 그것부터 말한다.
  expect(
    screen.getByText(/설정\(레시피 · 인자 · 시드 · 조건\)은 그대로 남아/),
  ).toBeInTheDocument();
  expect(
    screen.getByRole("button", { name: /공유 폴더로 보내기/ }),
  ).toBeDisabled();

  fireEvent.click(screen.getByRole("button", { name: "다시 만들기" }));
  await waitFor(() =>
    expect(seen).toContain("POST /api/doe/s1/rerun?only=all"),
  );
  await waitFor(() => expect(reload).toHaveBeenCalled());
});

test("파일이 있으면 그 안내는 안 뜨고 보낼 수 있다", () => {
  mockFetch([]);
  render(
    <MemoryRouter>
      <DoeStudyView study={study({})} onReload={() => {}} />
    </MemoryRouter>,
  );
  expect(screen.queryByText(/정리되었습니다/)).toBeNull();
  expect(
    screen.getByRole("button", { name: /공유 폴더로 보내기/ }),
  ).toBeEnabled();
});

test("실패한 점만 다시 — 성한 것을 다시 만들지 않으려고 따로 둔다", async () => {
  const seen: string[] = [];
  mockFetch(seen);
  render(
    <MemoryRouter>
      <DoeStudyView
        study={study({
          failed: 1,
          done: 1,
          points: [
            {
              id: "a",
              number: 1,
              params: { 두께: 2 },
              status: "ok",
              error: "",
              step_file: "points/p0001.step",
            },
            {
              id: "b",
              number: 2,
              params: { 두께: 4 },
              status: "failed",
              error: "깨짐",
              step_file: "",
            },
          ],
        } as unknown as Partial<DoeStudy>)}
        onReload={() => {}}
      />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: /실패한 1 점만 다시/ }));
  await waitFor(() =>
    expect(seen).toContain("POST /api/doe/s1/rerun?only=failed"),
  );
});
