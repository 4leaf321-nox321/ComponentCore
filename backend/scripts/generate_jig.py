"""서버 없이 코어만 돌린다 — 알고리즘을 고칠 때 쓰는 CLI.

python scripts/generate_jig.py                          # 시연 제품(브래킷)
python scripts/generate_jig.py part.step -o out/        # 제품 STEP
python scripts/generate_jig.py --spec '{"kind":"box","length":60,"width":40,"height":20}'
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core import pipeline
from app.core.options import JigOptions


def main() -> int:
    parser = argparse.ArgumentParser(description="지그 생성 CLI")
    parser.add_argument("step", nargs="?", help="제품 STEP 경로. 없으면 시연 제품")
    parser.add_argument("--spec", help="기본 도형 스펙(JSON). STEP 대신")
    parser.add_argument("-o", "--out", default="out", help="결과 폴더")
    parser.add_argument("--options", help="JigOptions 일부(JSON)")
    args = parser.parse_args()

    source: Path | dict[str, object] | None
    if args.step:
        source = Path(args.step)
    elif args.spec:
        source = json.loads(args.spec)
    else:
        source = None

    options = JigOptions.from_dict(json.loads(args.options) if args.options else None)
    result = pipeline.run(source, options, Path(args.out))
    summary = result.summary()
    for stage in summary["stages"]:
        print(f"{stage['name']:>13}  {stage['millis']:>5} ms  {stage['detail']}")
    for note in summary["plan"]["notes"]:
        print(f"  · {note}")
    print(
        "간섭:", "없음" if summary["interference"]["ok"] else summary["interference"]["items"]
    )
    for key, path in result.files.items():
        print(f"{key:>14}: {path}")
    return 0 if summary["interference"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
