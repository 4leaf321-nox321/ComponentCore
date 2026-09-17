"""지그 생성 코어 — build123d 위에 선 순수 파이썬 층.

**웹 프레임워크와 DB 를 모른다.** FastAPI · SQLAlchemy 를 여기서 import 하면 CLI 나
시험에서 코어만 따로 돌릴 수 없고, 그러면 기하 알고리즘을 고칠 때마다 서버를 띄워야 한다.
방향은 `modules -> core` 한 쪽이다(tests/architecture 가 검사한다).

    제품 STEP ─▶ geometry ─▶ features ─▶ planning ─▶ elements(support·locator·clamp)
             ─▶ assembly ─▶ interference ─▶ export(STEP · glTF)

각 단계는 `pipeline.run()` 이 차례로 부른다. 단계마다 입력과 출력이 `model.py` 의
데이터클래스로 고정돼 있어서, 한 단계를 다른 알고리즘으로 갈아 끼워도 나머지는 그대로다.
"""
