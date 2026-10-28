import {
  SPEC, LANGUAGE_LABELS, CONTROL_TARGETS, IO_KINDS, MODULES, OPERATION_MODES, SAFETY_NOTICE,
} from "./spec.js";
import { validateConfig } from "./validate.js";

const app = document.getElementById("app");
document.getElementById("notice").textContent = "⚠ " + SAFETY_NOTICE;

const state = {
  step: 1,
  cfg: {
    series: "", cpu: "", language: "", software: "", x_points: "", y_points: "",
    control_target: "", safety_ack: false,
    emergency_stop: { used: false, device: "" },
    io_list: [{ device: "", name: "", kind: IO_KINDS[0], desc: "" }],
    modules: [], device_rule: { M: 0, D: 0, T: 0, C: 0 }, timer_unit_ms: 100,
    modes: ["자동"], retentive: false, alarm: false, project_name: "", comment_lang: "ko", note: "",
  },
  errors: {},
  conditions: [{ text: "", must_pass: true }],
  condError: "",
  result: null,
};

function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "class") el.className = v;
    else if (v !== undefined && v !== false) el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat(Infinity)) if (c !== null && c !== undefined) el.append(c);
  return el;
}

function field(label, key, control, required = false, error = "") {
  return h("label", { class: "f" + (error ? " invalid" : "") },
    h("span", {}, label, required ? h("span", { class: "req" }, " *") : ""),
    control,
    h("span", { class: "err" }, error));
}

function select(options, value, onchange, placeholder = "선택하세요") {
  const s = h("select", { onchange });
  s.append(h("option", { value: "" }, placeholder));
  for (const o of options) {
    const [v, l] = Array.isArray(o) ? o : [o, o];
    const opt = h("option", { value: v }, l);
    if (v === value) opt.selected = true;
    s.append(opt);
  }
  return s;
}

function setStep(n) {
  state.step = n;
  for (let i = 1; i <= 3; i++) document.getElementById("step" + i).classList.toggle("active", i === n);
  render();
}

function render() {
  app.replaceChildren(state.step === 1 ? settingsView() : state.step === 2 ? conditionsView() : doneView());
}

function checkGroup(options, selected, onchange) {
  return h("div", { class: "checks" }, options.map((o) =>
    h("label", {}, h("input", {
      type: "checkbox", checked: selected.includes(o),
      onchange: (e) => onchange(o, e.target.checked),
    }), " " + o)));
}

function settingsView() {
  const c = state.cfg;
  const e = state.errors;
  const spec = SPEC[c.series];
  const input = (key, type = "text", extra = {}) =>
    h("input", { type, value: c[key], oninput: (ev) => (c[key] = ev.target.value), ...extra });

  const form = h("form", { novalidate: true, onsubmit: (ev) => { ev.preventDefault(); submitSettings(); } });
  const errKeys = Object.keys(e);
  if (errKeys.length) {
    form.append(h("div", { class: "summary" }, "입력을 확인해 주세요: ",
      errKeys.map((k) => (typeof e[k] === "string" ? e[k] : "입출력 신호 표의 오류")).join(" / ")));
  }

  form.append(h("fieldset", {}, h("legend", {}, "PLC 사양 (필수)"), h("div", { class: "grid" },
    field("MELSEC 시리즈", "series", select(Object.keys(SPEC), c.series, (ev) => {
      c.series = ev.target.value; c.cpu = ""; c.software = ""; c.language = "";
      render();
    }), true, e.series),
    field("CPU 모델", "cpu", select(spec ? Object.keys(spec.cpus) : [], c.cpu, (ev) => { c.cpu = ev.target.value; render(); },
      spec ? "선택하세요" : "시리즈를 먼저 선택"), true, e.cpu),
    field("프로그램 언어", "language", select(spec ? spec.languages.map((l) => [l, LANGUAGE_LABELS[l]]) : [], c.language,
      (ev) => (c.language = ev.target.value)), true, e.language),
    field("GX Works 버전", "software", select(spec ? spec.software : [], c.software,
      (ev) => (c.software = ev.target.value)), true, e.software),
    field("입력(X) 점수", "x_points", input("x_points", "number", { min: 0 }), true, e.x_points),
    field("출력(Y) 점수", "y_points", input("y_points", "number", { min: 0 }), true, e.y_points),
    h("div", { class: "err" }, e.compat || ""),
  )));

  const ioTable = h("table", {},
    h("tr", {}, ["디바이스", "이름", "종류", "설명", ""].map((t) => h("th", {}, t))),
    c.io_list.map((row, i) => [h("tr", { class: e.io_list && e.io_list[i] ? "invalid" : "" },
      h("td", {}, h("input", { value: row.device, placeholder: spec && spec.notation === "octal" ? "X0, Y10" : "X0, Y1F",
        oninput: (ev) => (row.device = ev.target.value) })),
      h("td", {}, h("input", { value: row.name, placeholder: "START_PB", oninput: (ev) => (row.name = ev.target.value) })),
      h("td", {}, select(IO_KINDS, row.kind, (ev) => (row.kind = ev.target.value), "종류")),
      h("td", {}, h("input", { value: row.desc, oninput: (ev) => (row.desc = ev.target.value) })),
      h("td", {}, h("button", { type: "button", class: "del", onclick: () => { c.io_list.splice(i, 1); render(); } }, "삭제")),
    ), (e.io_list && e.io_list[i]) ? h("tr", {}, h("td", { colspan: 5, class: "err" }, e.io_list[i])) : null]),
  );
  form.append(h("fieldset", {}, h("legend", {}, "입출력 신호 목록 (필수)"),
    spec ? h("p", { class: "hint" }, `${spec.notation === "hex" ? "16진수" : "8진수"} 표기 / X=입력, Y=출력`) : null,
    ioTable, h("span", { class: "err" }, e.io_list_empty || ""),
    h("button", { type: "button", class: "sub", onclick: () => { c.io_list.push({ device: "", name: "", kind: IO_KINDS[0], desc: "" }); render(); } }, "+ 신호 추가")));

  form.append(h("fieldset", {}, h("legend", {}, "제어 정보 (필수)"), h("div", { class: "grid" },
    field("제어 대상 유형", "control_target", select(CONTROL_TARGETS, c.control_target, (ev) => (c.control_target = ev.target.value)), true, e.control_target),
    h("div", {},
      h("label", {}, h("input", { type: "checkbox", checked: c.emergency_stop.used, onchange: (ev) => { c.emergency_stop.used = ev.target.checked; render(); } }), " 비상정지 / 안전 입력 사용"),
      c.emergency_stop.used ? field("비상정지 디바이스", "es", h("input", { value: c.emergency_stop.device, placeholder: "X0", oninput: (ev) => (c.emergency_stop.device = ev.target.value) }), true, e.emergency_stop) : null),
  ), h("label", {}, h("input", { type: "checkbox", checked: c.safety_ack, onchange: (ev) => (c.safety_ack = ev.target.checked) }), " " + SAFETY_NOTICE + " (동의)"),
  h("div", { class: "err" }, e.safety_ack || "")));

  form.append(h("fieldset", {}, h("legend", {}, "선택 항목 (미입력 시 기본값)"), h("div", { class: "grid" },
    field("사용 모듈", "modules", checkGroup(MODULES, c.modules, (o, on) => (c.modules = on ? [...c.modules, o] : c.modules.filter((m) => m !== o)))),
    field("운전 모드", "modes", checkGroup(OPERATION_MODES, c.modes, (o, on) => (c.modes = on ? [...c.modes, o] : c.modes.filter((m) => m !== o)))),
    field("M 시작 번호", "M", h("input", { type: "number", min: 0, value: c.device_rule.M, oninput: (ev) => (c.device_rule.M = Number(ev.target.value)) })),
    field("D 시작 번호", "D", h("input", { type: "number", min: 0, value: c.device_rule.D, oninput: (ev) => (c.device_rule.D = Number(ev.target.value)) })),
    field("타이머 시간 단위", "timer", select([["100", "100ms"], ["10", "10ms"], ["1", "1ms"]], String(c.timer_unit_ms), (ev) => (c.timer_unit_ms = Number(ev.target.value) || 100), "100ms (기본)")),
    field("정전 시 상태", "retentive", select([["false", "비유지 (기본)"], ["true", "유지(래치)"]], String(c.retentive), (ev) => (c.retentive = ev.target.value === "true"), "비유지 (기본)")),
    field("알람/에러 처리", "alarm", select([["false", "미사용 (기본)"], ["true", "알람 램프·부저 사용"]], String(c.alarm), (ev) => (c.alarm = ev.target.value === "true"), "미사용 (기본)")),
    field("프로젝트 이름", "project_name", input("project_name", "text", { maxlength: 32, placeholder: "비우면 자동 생성" }), false, e.project_name),
    field("주석 언어", "comment_lang", select([["ko", "한국어"], ["en", "English"], ["ja", "日本語"]], c.comment_lang, (ev) => (c.comment_lang = ev.target.value || "ko"), "한국어 (기본)")),
    field("비고 / 기타 제약", "note", input("note")),
  )));

  form.append(h("div", { class: "actions" }, h("span", {}), h("button", { type: "submit" }, "다음: 동작 조건 입력")));
  return form;
}

function submitSettings() {
  state.cfg.x_points = state.cfg.x_points === "" ? "" : Number(state.cfg.x_points);
  state.cfg.y_points = state.cfg.y_points === "" ? "" : Number(state.cfg.y_points);
  state.errors = validateConfig(state.cfg);
  if (Object.keys(state.errors).length) render();
  else setStep(2);
}

function conditionsView() {
  const wrap = h("div", {});
  wrap.append(h("fieldset", {}, h("legend", {}, "동작 조건 (필수/선택 구분)"),
    h("p", { class: "hint" }, "예) START 버튼을 누르면 모터가 켜지고, 비상정지를 누르면 모든 출력이 꺼진다."),
    state.conditions.map((cd, i) => h("div", { class: "cond" },
      h("input", { type: "text", value: cd.text, placeholder: "조건을 한 줄로 적어 주세요", oninput: (ev) => (cd.text = ev.target.value) }),
      h("label", {}, h("input", { type: "checkbox", checked: cd.must_pass, onchange: (ev) => (cd.must_pass = ev.target.checked) }), " 필수"),
      h("button", { type: "button", class: "del", onclick: () => { state.conditions.splice(i, 1); if (!state.conditions.length) state.conditions.push({ text: "", must_pass: true }); render(); } }, "삭제"))),
    h("button", { type: "button", class: "sub", onclick: () => { state.conditions.push({ text: "", must_pass: true }); render(); } }, "+ 조건 추가"),
    h("div", { class: "err" }, state.condError)));
  wrap.append(h("div", { class: "actions" },
    h("button", { type: "button", class: "sub", onclick: () => setStep(1) }, "이전"),
    h("button", { type: "button", onclick: submitConditions }, "저장")));
  return wrap;
}

function submitConditions() {
  const list = state.conditions.filter((c) => c.text.trim());
  if (!list.length) { state.condError = "동작 조건을 1개 이상 입력해 주세요."; render(); return; }
  if (!list.some((c) => c.must_pass)) { state.condError = "필수 조건을 1개 이상 지정해 주세요."; render(); return; }
  state.condError = "";
  const c = state.cfg;
  state.result = {
    plc_config: {
      series: c.series, cpu: c.cpu, language: c.language, software: c.software,
      x_points: c.x_points, y_points: c.y_points, control_target: c.control_target,
      emergency_stop: c.emergency_stop, modules: c.modules, device_rule: c.device_rule,
      timer_unit_ms: c.timer_unit_ms, modes: c.modes, retentive: c.retentive, alarm: c.alarm,
      project_name: c.project_name || "PRJ_" + Date.now().toString(36).toUpperCase(),
      comment_lang: c.comment_lang, note: c.note,
    },
    io_list: c.io_list.map((r) => ({ device: r.device.trim().toUpperCase(), name: r.name.trim(), kind: r.kind, desc: r.desc })),
    conditions: list.map((cd, i) => ({ id: "C" + (i + 1), text: cd.text.trim(), must_pass: cd.must_pass })),
  };
  localStorage.setItem("melsec_project", JSON.stringify(state.result));
  setStep(3);
}

function doneView() {
  return h("div", {},
    h("fieldset", {}, h("legend", {}, "저장된 프로젝트 설정"),
      h("p", { class: "hint" }, "아직 백엔드가 없어 브라우저에 임시 저장했어요. (#39 후속: POST /projects 연동)"),
      h("pre", {}, JSON.stringify(state.result, null, 2))),
    h("div", { class: "actions" }, h("button", { type: "button", class: "sub", onclick: () => setStep(2) }, "조건 수정"), h("span", {})));
}

setStep(1);
