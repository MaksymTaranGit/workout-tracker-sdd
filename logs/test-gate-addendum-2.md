# Журнал контрольної точки TEST-GATE-ADDENDUM-2: Затвердження тестів SRS Addendum #2 (М'яке видалення вправ)

**Дата:** 2026-11-16  
**Проєкт:** Workout Volume & Progressive Overload Tracker  
**Етап плану:** Етап 5 / SRS Addendum #2 — Кероване внесення зміни (`TKT-29`, фаза TDD RED)  
**Джерела істини (SSoT):** `spec/srs.tex`, `spec/srs-addendum.md`, `spec/srs-addendum-2.md`, `spec/openapi.yaml`  
**Об'єкти контролю:**
* Інтеграційні BDD-тести адендуму #2 (`tests/test_addendum2_exercise_archiving.py`)
* Контрактні OpenAPI-тести (`tests/test_openapi_contract.py`)
* Регресійні набори Блоків 1–4 (`tests/test_block1_sessions_and_sets.py`, `tests/test_block2_volume_load.py`, `tests/test_block3_1rm_engine.py`, `tests/test_block4_analytics_and_delta.py`)
* Системний NDJSON-лог (`logs/system-execution.log`)

Цей документ фіксує результати верифікації тестового набору Етапу 5 (фаза **TDD RED**) перед реалізацією патерну Soft Delete для архівації вправ за тікетом `TKT-30`.

---

## 1. Контекст та охоплення вимог SRS Addendum #2 (`TKT-29`)

Тестовий набір SRS Addendum #2 покриває м'яке видалення (архівацію) вправи з каталогу зі збереженням історичної цілісності сесій та аналітики:

* **Функціональна вимога:** `REQ-F-022` (М'яке видалення / архівація вправи з каталогу `DELETE /api/v1/exercises/{exerciseId}`).
* **Критерій приймання:** `AC13` (позначення `is_archived = true` та `archived_at`, виключення з `GET /api/v1/exercises`, блокування додавання до нових сесій з кодом `422 ERR_EXERCISE_ARCHIVED`, збереження історії сесій та аналітики).
* **BDD-сценарій:**
  * `BDD-008` — повний наскрізний сценарій архівації вправи: створення історичної сесії з робочим підходом (`100.0 кг x 5`), м'яке видалення вправи, зникнення з активного каталогу, відхилення при спробі додати до нової сесії (`422 ERR_EXERCISE_ARCHIVED`) та перевірка повної доступності історії сесії й аналітичного дашборду (`block_volume_load == 500.0`).
* **Бар'єр реєстру ризиків:**
  * `RSK-10` — запобігання каскадній втраті історичних тренувань та повторному використанню архівованих вправ у нових сесіях; також перевірено граничні та негативні кейси (`404 ERR_RESOURCE_NOT_FOUND` для неіснуючого `exerciseId` та повторного видалення вже архівованої вправи).

---

## 2. Чеклист критеріїв контрольної точки TEST-GATE-ADDENDUM-2

| № | Критерій оцінки TEST-GATE-ADDENDUM-2 | Фактичний стан та доказова база | Статус |
| :- | :--- | :--- | :-: |
| 1 | **Причинна незалежність тестів від реалізації (TDD Purity)** | Код у `src/` не змінювався: у `src/api/routes.py` відсутній маршрут `DELETE /api/v1/exercises/{exerciseId}`, а у `src/repositories/workout_repository.py` та `src/services/workout_service.py` відсутня логіка `is_archived` та код `ERR_EXERCISE_ARCHIVED`. | [x] PASSED |
| 2 | **Повнота покриття вимог `TKT-29` (`REQ-F-022`, `AC13`, `BDD-008`, `RSK-10`)** | У `tests/test_addendum2_exercise_archiving.py` реалізовано 3 інтеграційні тести: `test_bdd_008_archive_exercise_soft_delete_preserves_history`, `test_delete_nonexistent_exercise_returns_404` та `test_delete_already_archived_exercise_returns_404`. | [x] PASSED |
| 3 | **Очікуване падіння нових тестів у фазі RED і зелена регресія Блоків 1–4** | Прогін `.venv\Scripts\pytest.exe -v --tb=short` завершився з результатом **`51 passed, 3 failed`** (`8.77s`): усі 51 регресійний і контрактний тести стабільно проходять, а всі 3 нові тести падають зі статусом `405 Method Not Allowed` через відсутність `DELETE /api/v1/exercises/{exerciseId}`. | [x] PASSED |
| 4 | **Валідність системного логу (`logs/system-execution.log`)** | Файл логу містить **5992 валідні NDJSON-рядки** без синтаксичних помилок і NUL-байтів. | [x] PASSED |

---

## 3. Статус та рішення

**Рішення:** **GO (Затверджено)**.

Контрольну точку **TEST-GATE-ADDENDUM-2** успішно пройдено. Дозволено перехід до фази **GREEN** Етапу 5 — реалізації тікета **`TKT-30`** (м'яке видалення вправ, фільтрація активного каталогу, блокування `422 ERR_EXERCISE_ARCHIVED` та збереження історичної цілісності).
