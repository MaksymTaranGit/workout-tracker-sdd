# Матриця простежуваності та розподілу відповідальності (Traceability & RACI Matrix)

Цей документ забезпечує двосторонню простежуваність між функціональними вимогами (`REQ-F-001` – `REQ-F-021`), критеріями прийняття (`AC1` – `AC12`), BDD-сценаріями (`BDD-001` – `BDD-007`), робочими тікетами беклогу та операціями контракту REST API (`spec/openapi.yaml`), а також фіксує розподіл ролей між кодинговим агентом та людиною.

---

## 1. Розподіл відповідальності за типами задач

| Роль | Тип задачі | Зона відповідальності |
| :--- | :--- | :--- |
| **Кодинговий агент (AI)** | `Test` | Написання BDD/юніт-тестів перед кодом фічі (фаза **Red**). |
| | `Feature` | Реалізація виробничої бізнес-логіки для проходження тестів (фаза **Green**). |
| | `Verification` | Запуск автотестів, замір продуктивності, генерація структурованих логів у STDOUT/STDERR. |
| | `Documentation` | Складання та оновлення технічної супровідної документації. |
| **Людина (Tech Lead / QA)** | `Specification / Addendum` | Авторство, коригування та фінальне затвердження вимог. |
| | `Validation` | Семантична перевірка реалізованих фіч на відповідність користувацьким сценаріям (AC, BDD). |
| | `Gate` | Одноосібне прийняття рішень **GO / REVISE** на контрольних точках блоків. |

---

## 2. Матриця простежуваності вимог (Requirements Traceability Matrix)

| ID Вимоги | Короткий опис | Критерій прийняття (AC) | ID BDD-сценарію | Тікет (Feature) | Тест (Test) | Операція REST API (Method & URI / operationId) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **REQ-F-001** | Створення нової тренувальної сесії | AC1 | - | TKT-02 | TKT-01 | `POST /api/v1/sessions` (`createSession`), `GET /api/v1/sessions` (`listSessions`), `GET /api/v1/sessions/{sessionId}` (`getSessionById`) |
| **REQ-F-002** | Автоматична фіксація маси тіла (снапшот) | AC1 | BDD-001 | TKT-02 | TKT-01 | `POST /api/v1/sessions` (`createSession` — серверний інваріант `body_weight_snapshot`), `GET /api/v1/sessions/{sessionId}` (`getSessionById`) |
| **REQ-F-003** | Додавання вправ до сесії | AC2 | - | TKT-04 | TKT-03 | `POST /api/v1/sessions/{sessionId}/blocks` (`createExerciseBlock`), `GET /api/v1/sessions/{sessionId}/blocks/{blockId}` (`getExerciseBlockById`) |
| **REQ-F-004** | Фіксація підходів (вага, повторення, RPE) | AC2 | - | TKT-04 | TKT-03 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet`), `DELETE /api/v1/sessions/{sessionId}/blocks/{blockId}/sets/{setId}` (`deleteWorkoutSet`) |
| **REQ-F-005** | Позначка підходу як "Розминочний" | AC2 | BDD-003 | TKT-04 | TKT-03 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet` — атрибут `is_warmup`) |
| **REQ-F-006** | Розрахунок Volume Load для підходу та блоку вправи | AC3 | - | TKT-09 | TKT-08 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet` — обчислення `set_volume_load` та `block_volume_load`), `DELETE .../sets/{setId}` (`deleteWorkoutSet`), `GET .../blocks/{blockId}` (`getExerciseBlockById`) |
| **REQ-F-007** | Ігнорування розминочних підходів при розрахунку об'єму | AC4 | BDD-003 | TKT-09 | TKT-08 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet` — інваріант `set_volume_load = 0.0` при `is_warmup = true`) |
| **REQ-F-008** | Формула Volume Load для стандартних вправ | AC3 | - | TKT-09 | TKT-08 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet` — серверний розрахунок `weight * reps` для `STANDARD`) |
| **REQ-F-009** | Формула Volume Load для вправ із власною вагою | AC5 | - | TKT-11 | TKT-10 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet` — серверний розрахунок `(body_weight_snapshot + weight) * reps` для `BODYWEIGHT`/`ASSISTED`) |
| **REQ-F-010** | Від'ємне значення "Додаткової ваги" (компенсація) | AC5 | BDD-002 | TKT-11 | TKT-10 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet` — підтримка `weight < 0` для `ASSISTED`, розрахунок `effective_weight`) |
| **REQ-F-011** | Розрахунок 1RM для робочих підходів | AC6 | BDD-006 | TKT-16 | TKT-15 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet` — обчислення `estimated_1rm` та `block_max_1rm`), `GET /api/v1/sessions/{sessionId}` (`getSessionById`) |
| **REQ-F-012** | Гранулярний вибір математичної моделі 1RM | AC6 | BDD-006 | TKT-16 | TKT-15 | `PATCH /api/v1/exercises/{exerciseId}` (`updateExerciseModel`), `POST /api/v1/exercises` (`createExercise`), `GET /api/v1/exercises/{exerciseId}` (`getExerciseById`) |
| **REQ-F-013** | Формула Epley як алгоритм 1RM за замовчуванням | AC6 | BDD-006 | TKT-16 | TKT-15 | `POST /api/v1/exercises` (`createExercise` — серверний дефолт `rm_model = "EPLEY"`) |
| **REQ-F-014** | Попередження (Soft Constraint) при > 10 повтореннях | AC7 | BDD-004 | TKT-18 | TKT-17 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet` — прапорець `soft_constraint_warning = true` при `reps > 10`) |
| **REQ-F-015** | Дельта Volume Load відносно останньої сесії | AC8 | BDD-005 | TKT-23 | TKT-22 | `GET /api/v1/exercises/{exerciseId}/analytics` (`getExerciseAnalytics`), `GET /api/v1/sessions/{sessionId}/blocks/{blockId}` (`getExerciseBlockById`), `POST .../sets` (`createWorkoutSet` — поле `volume_load_delta`) |
| **REQ-F-016** | Дельта максимального 1RM відносно останньої сесії | AC8 | BDD-005 | TKT-23 | TKT-22 | `GET /api/v1/exercises/{exerciseId}/analytics` (`getExerciseAnalytics`), `GET /api/v1/sessions/{sessionId}/blocks/{blockId}` (`getExerciseBlockById`), `POST .../sets` (`createWorkoutSet` — поле `max_1rm_delta`) |
| **REQ-F-017** | Дашборд із графіком динаміки 1RM та Volume Load | AC9 | BDD-007 | TKT-25 | TKT-24 | `GET /api/v1/exercises/{exerciseId}/analytics` (`getExerciseAnalytics` — часовий ряд `data_points` та `latest_progression`) |
| **REQ-F-018** | Відсутність розрахунку Дельти без попередніх записів | AC8 | - | TKT-23 | TKT-22 | `GET /api/v1/exercises/{exerciseId}/analytics` (`getExerciseAnalytics`), `GET .../blocks/{blockId}` (`getExerciseBlockById`), `POST .../sets` (`createWorkoutSet` — інваріант `has_previous_baseline = false`, `delta = null`) |
| **REQ-F-019** | Поточна маса тіла в профілі (30.0–300.0 кг) та незмінність історичних снапшотів (`spec/srs-addendum.md`) | AC10 | BDD-001 | TKT-02 | TKT-01 | `GET /api/v1/profile` (`getUserProfile`), `PUT /api/v1/profile` (`updateUserProfile`) |
| **REQ-F-020** | Каталог вправ (`STANDARD`, `BODYWEIGHT`, `ASSISTED`) та налаштування 1RM (`spec/srs-addendum.md`) | AC11 | BDD-002, BDD-006 | TKT-06 (TKT-04, TKT-16) | TKT-03, TKT-15 | `POST /api/v1/exercises` (`createExercise`), `GET /api/v1/exercises` (`listExercises`), `GET /api/v1/exercises/{exerciseId}` (`getExerciseById`), `PATCH /api/v1/exercises/{exerciseId}` (`updateExerciseModel`) |
| **REQ-F-021** | Ефективне обтяження $W_{eff}$ у 1RM та хронологічний порядок блоків для Дельти (`spec/srs-addendum.md`) | AC12 | BDD-002, BDD-005, BDD-006 | TKT-09, TKT-11, TKT-23 | TKT-03, TKT-08 | `POST /api/v1/sessions/{sessionId}/blocks/{blockId}/sets` (`createWorkoutSet`), `GET /api/v1/exercises/{exerciseId}/analytics` (`getExerciseAnalytics`) |
