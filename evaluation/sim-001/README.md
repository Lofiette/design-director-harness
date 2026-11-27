# SIM-001 · результаты локального пилота

Пилот проверяет перенос отмены между сессиями. В начальном источнике две задачи ожидают ответа. Позже приходит отмена одной из них. Приёмка сверяет изменённый ID, прямой источник, дату события и дату записи, состояние соседней задачи и отсутствие повторного напоминания. Исполнитель применяет предложенные изменения к независимым копиям синтетических данных и перечитывает их с диска.

## Результаты модели

| Сравнение | Условие | Результат |
|---|---|---|
| Один исходный кейс | Короткое исходное правило на основе `ddh-recover` | 10 из 11 проверок. Единственная ошибка в сводке о соседней задаче. |
| Тот же кейс | Кандидат с явной привязкой к задаче, источнику и датам | 11 из 11 проверок. Изменилась одна запись. |
| Два отложенных кейса | Адаптация, предложенная без истории измерений | 2 из 2 кейсов, по 11 из 11 проверок. |
| Те же отложенные кейсы | Адаптация с доступом к измеренному журналу | 2 из 2 кейсов, по 11 из 11 проверок. |

Исходный вариант правильно отменил Q-14, привёл источник s-2 и сохранил обе даты. Он представил старый статус Q-29 как подтверждённый текущий. Кандидат сообщил, что раньше Q-29 ждала ответа, а её нынешний исход неизвестен. Ни один вариант не менял строку Q-29 и не создавал напоминание. [Исходные ответы](native-input.json) · [Проверки и перечитанное состояние](native-source/report.json)

Модель — GPT-6.2 Astra, усилие Ultra, встроенные независимые контексты одного Codex Work на Surface. Версия DDH в манифесте — 5.0.1, база пилота — `2827976b0ad89fdfaffc731d2a23b293cc502a79`. Бюджет каждой проверочной сессии — один ответ до 220 слов. Модель возвращала предложения изменений. Запись и чтение выполнил локальный Python 3.12.14. Сторонние модельные API в эксперименте не использовались.

Для переноса две новые сессии получили одинаковые факты, текущее кандидатное правило и лимит в 75 слов на новую формулировку. Одна дополнительно получила измеренные исходы из SIM. Обе формулировки зафиксированы до проверки, SHA-256 файла — `506f26f5cd74539b9b284372f8197412c07654b0778b28f97557c69712cc7888`. Четыре свежих контекста получили только своё правило и один новый кейс. Журнал, принадлежность к группе и эталонные ответы им не передавались. Оценщик сравнил перечитанные данные по одному набору условий. [Зафиксированные правила и условия](frozen-rules.json)

| Отложенный кейс | Изменение примера | Ответы без журнала / с журналом | Доказательства |
|---|---|---|---|
| Kite | Отменена вторая задача в списке. Дата записи объявлена первой. | tern / lark | [Вход](holdout-kite-input.json) · [Результат](holdout-kite/report.json) |
| Fir | Порядок задач отличается от источника. Дата события и дата записи приходятся на разные годы. | moss / elm | [Вход](holdout-fir-input.json) · [Результат](holdout-fir/report.json) |

На двух отложенных примерах обе адаптации дали одинаковый результат. Все измерения относятся к одной модели и одному харнессу. Проверки на других моделях и в других хостах имеют статус `not_run`. В рабочий реестр правила по итогам пилота не вносились.

## Код и установка

- Детерминированные реализации отдельно выполнили 7 из 7 проверок каждая. [Отчёт кодового прогона](measured/report.json)
- Через штатный `node tools/ddh.mjs` проверены чистая установка с пятью навыками, включение и отключение SIM, повтор без дублей, конфликт ID, неудачный и неизмеренный исходы, фильтры, пересборка индекса и выдача утверждённого правила. При повторной неудаче того же правила в той же среде старая успешная попытка остаётся в истории, а карточка снимает отметку о подтверждённом варианте. [Сквозные тесты](../../test/sim.test.mjs)
- В отдельном проекте сначала сохранили обычное событие Continuous Memory, затем подключили SIM и записали попытку. Хеши первоначального события и исходного объекта совпали до и после. В экземпляре с результатами эксперимента ядро подтвердило восемь событий и восемь исходных объектов; шесть из восьми записей относились к модельным ответам.
- На Windows три исходных теста завершились ошибкой при подготовке символьных ссылок (`WinError 1314`), ещё один пропущен. Результат воспроизведён на базовом коммите и на пилоте. В Continuous Memory прошли 59 из 62, две ошибки и один пропуск. В DIS intake прошли 11 из 12, одна ошибка.

[Установка и команды SIM](../../docs/SIM.md)


## Code rehearsal

From the DDH root, run:

```sh
python -B evaluation/sim-001/rehearse.py --out evaluation/sim-001/repeat
```

Choose a new output directory for each measurement. The baseline code reconciles an explicit update by unique task title. The candidate also requires a matching stable ID. Both keep the neighbor's unresolved outcome and the two source dates. These policies illustrate evidence-based resumption from [DDH recovery](../../skills/ddh-recover/SKILL.md) and date semantics from [Continuous Memory](../../modules/continuous-memory/README.md). The score describes the two scripts on this fixture.

The [recorded code run](measured/report.json) scored both policies 7/7. Both changed only A, cited the second source, kept B awaiting with its current outcome unknown and created zero reminders. The runner generated two inputs for the SIM `record` command, [baseline](measured/baseline.json) and [candidate](measured/candidate.json). Each contains prediction, observation and readback evidence. Reuse a saved file to retry the same attempt. A fresh run receives a new measurement ID and capture time.

## Native Work reply evaluation

Fresh Work sessions return proposed writes, a handoff and reminders. The evaluator replays each saved reply on its own synthetic files, reads both tasks back and scores the handoff separately. It checks whether a neighbor whose last observation was awaiting a reply is explicitly reported as currently unknown. The code rehearsal executes no model. Native Work scores require a separately captured reply pair.

```sh
python -B evaluation/sim-001/native_score.py --input evaluation/sim-001/native-input.json --output-dir evaluation/sim-001/scored-pair
```

The capture includes a fixture, model/harness/version, two uniquely named arms, exact rule texts and replies. An optional UTC `captured_at` gives the observation time. Without that field the report identifies the input file modification time as its clock basis. Each output directory contains the per-check report and two ingestible SIM attempt files. Model proposals are applied only to temporary JSON files; the caller supplies the responses and controls any blind assignment or case withholding.
