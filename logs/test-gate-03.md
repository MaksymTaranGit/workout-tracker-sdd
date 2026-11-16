# Журнал контрольної точки TEST-GATE-03: Затвердження тестів Етапу 3 (1RM Engine & Soft Constraint)

**Дата:** 2026-11-16  
**Проєкт:** Workout Volume & Progressive Overload Tracker  
**Етап плану:** Етап 3 / Блок 3 — Математичний рушій одноповторного максимуму 1RM (`TKT-15`, `TKT-17`, фаза TDD RED)  
**Джерела істини (SSoT):** `spec/srs.tex`, `spec/srs-addendum.md`, `spec/openapi.yaml`  
**Об'єкти контролю:**
* Модульні та інтеграційні тести Блоку 3 (`tests/test_block3_1rm_engine.py`)
* Регресійні набори Блоків 1–2 (`tests/test_block1_sessions_and_sets.py`, `tests/test_block2_volume_load.py`)
* Математичне ядро в частині `calculate_1rm` (`src/services/math_engine.py`)
* Системний NDJSON-лог (`logs/system-execution.log`)

Цей документ фіксує результати верифікації тестового набору Етапу 3 (фаза **TDD RED**) перед початком реалізації математичних формул Epley/Brzycki, `PATCH /api/v1/exercises/{exerciseId}` та попередження Soft Constraint за тікетами `TKT-16` та `TKT-18`.

---

## 1. Контекст та охоплення вимог Блоку 3 (`TKT-15`, `TKT-17`)

Тестовий набір Блоку 3 покриває обчислення одноповторного максимуму (`1RM`), перемикання математичної моделі для кожної вправи, індикатор точності при > 10 повтореннях та виключення розминки:

* **Функціональні вимоги:** `REQ-F-011`, `REQ-F-012`, `REQ-F-013`, `REQ-F-014`, `REQ-F-021`.
* **Критерії приймання:** `AC6`, `AC7`, `AC12`.
* **BDD-сценарії:**
  * `BDD-004` — активація `soft_constraint_warning = True` та формування інформативного `warning_message` (`REQ-F-014`) при `reps > 10` (`100 кг × 12 повт. -> 140.0 кг`).
  * `BDD-006` — числовий еталон Epley (`100 кг × 5 повт. -> 116.66 кг` через точну арифметику `Decimal` із `ROUND_DOWN`).
* **Бар'єри реєстру ризиків:**
  * `RSK-01` — усунення похибок IEEE 754 `float` та некоректного округлення через `Decimal` із `ROUND_DOWN`.
  * `RSK-02` — захист математичної стабільності формули Brzycki включно з граничним значенням `reps = 36` (`50 × 36 = 1800.0`).

---

## 2. Чеклист критеріїв контрольної точки TEST-GATE-03

| № | Критерій оцінки TEST-GATE-03 | Фактичний стан та доказова база | Статус |
| :- | :--- | :--- | :-: |
| 1 | **Причинна незалежність тестів від реалізації (TDD Purity)** | У `src/services/math_engine.py` метод `calculate_1rm` лишається заглушкою (`NotImplementedError`), а маршрут `PATCH /api/v1/exercises/{exerciseId}` повертає `501 Not Implemented`. | [x] PASSED |
| 2 | **Повнота покриття вимог `TKT-15` та `TKT-17`** | У `tests/test_block3_1rm_engine.py` створено 8 тестових функцій (прямі юніт-тести `MathEngine.calculate_1rm` та інтеграційні HTTP-сценарії для `EPLEY`, `BRZYCKI`, `AC12`, `BDD-004`, `BDD-006`, `PATCH`, `DELETE` і розминки). | [x] PASSED |
| 3 | **Очікуване падіння нових тестів у фазі RED і зелена регресія Блоків 1–2** | Прогін `.venv\Scripts\pytest.exe -v` завершився з результатом **`33 passed, 8 failed`** (`4.85s`): усі 33 регресійні тести Блоків 1–2 стабільно проходять, а всі 8 тестів Блоку 3 падають на `NotImplementedError`, `501` та базових заглушках `estimated_1rm = None`. | [x] PASSED |
| 4 | **Валідність системного логу (`logs/system-execution.log`)** | Файл логу містить **3445 валідних NDJSON-записів** без NUL-байтів (`TEST_RUNNER`: 75, `API`: 612, `DB`: 2441, `SERVICE`: 185, `MATH_ENGINE`: 132; рівні `INFO`: 196, `TRACE`: 3214, `WARNING`: 35). | [x] PASSED |

---

## 3. Статус та рішення

**Рішення:** **GO (Затверджено)**.

Контрольну точку **TEST-GATE-03** успішно пройдено. Дозволено перехід до фази **GREEN** Етапу 3 — реалізації тікетів **`TKT-16`** (рушій 1RM Epley/Brzycki, `PATCH /exercises/{exerciseId}`, агрегація `block_max_1rm`) та **`TKT-18`** (індикатор `Soft Constraint` при `reps > 10`).
