# Протокол підсумкової контрольної точки FINAL-GATE: Фінальний реліз системи (Лабораторна робота №5, `TKT-32`)

**Дата:** 2026-11-16  
**Проєкт:** Workout Volume & Progressive Overload Tracker  
**Етап плану:** Повний цикл розробки SDD/TDD — Етапи 1–5 (`TKT-01` – `TKT-32`, включно з SRS Addendum #1 та SRS Addendum #2)  
**Джерела істини (SSoT):** `spec/srs.tex`, `spec/srs-addendum.md`, `spec/srs-addendum-2.md`, `spec/openapi.yaml`  
**Об'єкти контролю:**
* Виробничий код застосунку (`src/main.py`, `src/api/routes.py`, `src/core/*`, `src/domain/*`, `src/repositories/*`, `src/services/*`)
* Повний набір автоматизованих тестів (`tests/test_block1_sessions_and_sets.py` – `tests/test_block4_analytics_and_delta.py`, `tests/test_openapi_contract.py`, `tests/test_addendum2_exercise_archiving.py`)
* Супровідна інженерна документація (`docs/traceability.md`, `docs/plan.md`, `docs/risk-register.md`)
* Протоколи проміжних гейтів (`logs/api-gate.md`, `logs/test-gate-01.md` – `logs/test-gate-04.md`, `logs/gate-01.md` – `logs/gate-04.md`, `logs/test-gate-addendum-2.md`) та системний NDJSON-лог (`logs/system-execution.log`)

Цей документ фіксує підсумкову технічну верифікацію, результати ручної валідації живої системи людиною та фінальне релізне рішення **GO** для повної системи **Workout Volume & Progressive Overload Tracker**.

---

## 1. Повне покриття специфікації (SDD & Traceability)

* **Функціональні вимоги (`REQ-F-001` – `REQ-F-022`):**
  * Базовий обсяг MVP (`spec/srs.tex`, `spec/srs-addendum.md`): управління профілем користувача (`REQ-F-019`), каталогом вправ (`REQ-F-020`), сесіями з незмінним `body_weight_snapshot` (`REQ-F-001`–`REQ-F-002`), ізольованими блоками та підходами з розминкою (`REQ-F-003`–`REQ-F-005`), рушієм Volume Load із урахуванням `STANDARD`/`BODYWEIGHT`/`ASSISTED` (`REQ-F-006`–`REQ-F-010`), рушієм 1RM (`EPLEY`/`BRZYCKI`) та Soft Constraint > 10 повторень (`REQ-F-011`–`REQ-F-014`), обчисленням хронологічної Дельти прогресу та аналітичним дашбордом (`REQ-F-015`–`REQ-F-018`, `REQ-F-021`).
  * Кероване розширення за **SRS Addendum #2** (`spec/srs-addendum-2.md`): м'яке видалення (Soft Delete / архівація) вправи з каталогу (`REQ-F-022`) через `DELETE /api/v1/exercises/{exerciseId}`, приховування з активного каталогу `GET /api/v1/exercises`, блокування додавання до нових сесій (`422 ERR_EXERCISE_ARCHIVED`) і збереження повної доступності історичних сесій та аналітики.
* **Критерії приймання (`AC1` – `AC13`):** усі 13 критеріїв приймання повністю реалізовані та підтверджені.
* **BDD-сценарії (`BDD-001` – `BDD-008`):** усі 8 еталонних сценаріїв покриті інтеграційними тестами та перевірені на живому сервері.
* **Реєстр ризиків (`RSK-01` – `RSK-10`):** усі ідентифіковані ризики (включно з точністю `Decimal` — `RSK-01`, межами `Brzycki`/`reps` — `RSK-02`, ізоляцією блоків та хронологічною базою — `RSK-09`, незмінністю історії після архівації вправ — `RSK-10`) мітиговано та протестовано.

---

## 2. Підсумки автоматизованої верифікації

1. **Регресійний та контрактний набір (`& ".\.venv\Scripts\pytest.exe" -v`):**
   * Результат фінального прогону: **`54 passed, 1 warning in 7.38s`** (`0` падінь, `0` пропусків):
     * Блок 1 (`test_block1_sessions_and_sets.py`): `20 passed`;
     * Блок 2 (`test_block2_volume_load.py`): `13 passed`;
     * Блок 3 (`test_block3_1rm_engine.py`): `8 passed`;
     * Блок 4 (`test_block4_analytics_and_delta.py`): `8 passed`;
     * Контракт OpenAPI (`test_openapi_contract.py`): `2 passed` — **100% відповідність усіх 15/15 операцій** та схем `components/schemas` контракту `spec/openapi.yaml`;
     * SRS Addendum #2 (`test_addendum2_exercise_archiving.py`): `3 passed` (`BDD-008`, `404` для неіснуючої та повторно архівованої вправи).
2. **Контроль продуктивності та SLA (`logs/system-execution.log`):**
   * Цілісність системного журналу: **6437 валідних NDJSON-рядків** без синтаксичних помилок і NUL-байтів.
   * **`REQ-NF-001` (CRUD та обчислення < 100 мс):** на **307 HTTP-запитах** — min **`3.98 мс`**, avg **`17.74 мс`**, max **`50.97 мс`** (**0 порушень**).
   * **`REQ-NF-002` (Аналітичний дашборд < 1000 мс):** на **9 HTTP-запитах** до `/analytics` — min **`5.44 мс`**, avg **`8.28 мс`**, max **`21.58 мс`** (**0 порушень**).

---

## 3. Підсумки ручної валідації людиною (Живий сервер ASGI)

Під час фінального приймального тестування людиною на живому сервері **`uvicorn`** через **Swagger UI (`/docs`)** перевірено ключові користувацькі сценарії:
* **`BDD-001`:** фіксація `body_weight_snapshot` у сесії та її незмінність після оновлення маси тіла в профілі (`PUT /api/v1/profile`).
* **`BDD-002`:** розрахунок від'ємної додаткової ваги (компенсації) для вправ типу `ASSISTED` (гравітрон).
* **`BDD-004`:** генерація попередження `soft_constraint_warning = true` при кількості повторень `reps > 10`.
* **`BDD-006`:** перемикання моделі розрахунку 1RM (`EPLEY` / `BRZYCKI`) через `PATCH /api/v1/exercises/{exerciseId}` та перевірка еталонних значень.
* **`BDD-008`:** м'яке видалення вправи (`DELETE /api/v1/exercises/{exerciseId}`), приховування з активного каталогу, відхилення спроби додавання до нової сесії (`422 ERR_EXERCISE_ARCHIVED`) та збереження історичних даних сесії й аналітики.

---

## 4. Чеклист фінальної контрольної точки (`TKT-32`)

| № | Критерій фінальної прийомки | Фактичний стан та докази | Статус |
| :- | :--- | :--- | :-: |
| 1 | **100% проходження всіх автотестів** | Фінальний прогін `pytest`: **`54 passed` за `7.38s`**. | [x] PASSED |
| 2 | **100% відповідність контракту `spec/openapi.yaml`** | Усі **15/15 операцій** та схем `ErrorResponse`/DTO повністю верифіковані (`test_openapi_contract.py`). | [x] PASSED |
| 3 | **Дотримання SLA (`REQ-NF-001`, `REQ-NF-002`)** | Max `50.97 мс` (< 100 мс) для CRUD/розрахунків та max `21.58 мс` (< 1000 мс) для аналітики (`0` порушень). | [x] PASSED |
| 4 | **Актуальність матриці простежуваності та плану** | Усі вимоги `REQ-F-001`–`REQ-F-022` та `REQ-NF-001`–`REQ-NF-010` мають статус `VERIFIED & VALIDATED`; усі тікети `TKT-01`–`TKT-32` мають статус `DONE`. | [x] PASSED |
| 5 | **Ручна валідація живого сервера людиною** | Сценарії `BDD-001`, `BDD-002`, `BDD-004`, `BDD-006`, `BDD-008` успішно перевірено у Swagger UI (`/docs`). | [x] PASSED |

---

## 5. Фінальне релізне рішення

**Рішення: GO (Затверджено до релізу та експлуатації)**.

Система **Workout Volume & Progressive Overload Tracker** повністю реалізована згідно зі специфікаціями `spec/srs.tex`, `spec/srs-addendum.md`, `spec/srs-addendum-2.md` та `spec/openapi.yaml`, пройшла наскрізну автоматизовану верифікацію (`54/54` тестів, SLA без порушень) і ручну валідацію на живому ASGI-сервері. Реліз затверджено, дозволено фінальне злиття гілки `addendum-2-exercise-archiving` у `main` і публікацію в GitHub.
