export const profiles = ["codex-plain", "product-os-4.1", "ddh-5.0"];

const action = '<button type="submit" aria-label="Save form">Save</button>\n';

export const cases = {
  copy: {
    files: { "action.html": action, "check.mjs": 'import assert from "node:assert/strict";\nimport { readFileSync } from "node:fs";\nassert.equal(readFileSync(new URL("./action.html", import.meta.url), "utf8"), \'<button type="submit" aria-label="Save form">Apply changes</button>\\n\');\n' },
    prompt: 'В action.html поменяй видимый текст кнопки с Save на Apply changes. Сохрани имя для скринридера и остальные файлы. Проверь изменение.',
    expected: { "action.html": action.replace(">Save<", ">Apply changes<") },
    rubric: {
      focusedCheck: "Есть свидетельство, что агент запустил node check.mjs или эквивалентную адресную проверку.",
      noUnneededQuestion: "Агент начал работу без вопроса, который можно было разрешить чтением fixture.",
    },
  },
  ux: {
    files: {
      "form.html": '<form><label for="name">Name</label><input id="name" name="name" required><button>Send</button></form>\n',
      "system.md": "# Project components\n\nUse Field, InlineAlert and PrimaryButton. Use space.200 for field gaps and color.feedback.error for errors.\n",
    },
    prompt: "Спроектируй улучшение формы заявки. Ознакомься с текущей формой и оставь решение в design.md.",
    secondPrompt: "Форму используют выездные сотрудники на узких экранах и с клавиатуры. Главный дефект — потеря введённых данных при тайм-ауте. Нужны сценарий, состояния и проверяемая приёмка на 390 и 1280 px. Пользуйся компонентами и токенами проекта.",
    expected: {},
    deliverable: "design.md",
    rubric: {
      consequentialQuestion: "Первый вопрос выявляет пользователя, его задачу или критичный сбой и мог изменить решение.",
      reflectsAnswer: "Решение учитывает узкий экран, клавиатуру и потерю данных после тайм-аута.",
      stateAndRecovery: "Описаны обычный ввод, отправка, тайм-аут с сохранением данных, повтор и успех.",
      systemAndFocus: "Названы проектные компоненты и токены, порядок фокуса и сообщение об ошибке.",
      verificationAtTwoWidths: "Указаны воспроизводимые действия и ожидаемый результат на 390 и 1280 px.",
    },
  },
  recovery: {
    files: { "status.txt": "pending\n", "evidence.txt": "Baseline: status is pending.\n" },
    prompt: "Задача — изменить status.txt с pending на reviewed, сохранив evidence.txt. В этом сеансе проверь исходное состояние, сохрани локальную запись с целью, границами, проверкой и следующим шагом. Статус пока не меняй. Продолжение будет в новом чате.",
    secondPrompt: "Продолжи работу по сохранённому состоянию проекта.",
    expected: { "status.txt": "reviewed\n" },
    rubric: {
      freshChat: "Второй этап запущен в новом чате с тем же профилем. Старая переписка не передавалась.",
      recoveredBeforeEdit: "Агент извлёк из записи цель, ограничения, исходное доказательство и следующий шаг до правки.",
      checkedResult: "Агент проверил новый статус и сохранность evidence.txt.",
    },
  },
};
