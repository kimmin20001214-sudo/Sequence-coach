import { IO_KINDS, emptyRow, type IoRow } from "./spec";

const MAX_ROWS = 1000;

// 따옴표("a,b")와 줄바꿈을 지원하는 간단한 CSV 파서
function parseCsv(text: string): string[][] {
  const rows: string[][] = [];
  let row: string[] = [];
  let cell = "";
  let quoted = false;
  const src = text.replace(/^\uFEFF/, "");
  for (let i = 0; i < src.length; i++) {
    const ch = src[i];
    if (quoted) {
      if (ch === '"' && src[i + 1] === '"') { cell += '"'; i++; }
      else if (ch === '"') quoted = false;
      else cell += ch;
    } else if (ch === '"') quoted = true;
    else if (ch === "," || ch === "\t") { row.push(cell); cell = ""; }
    else if (ch === "\n" || ch === "\r") {
      if (ch === "\r" && src[i + 1] === "\n") i++;
      row.push(cell); cell = "";
      rows.push(row); row = [];
    } else cell += ch;
  }
  if (cell !== "" || row.length) { row.push(cell); rows.push(row); }
  return rows.filter((r) => r.some((c) => c.trim() !== ""));
}

const HEADER_WORDS = ["device", "디바이스", "address", "주소"];

export interface CsvResult {
  rows: IoRow[];
  warnings: string[];
}

// 열 순서: 디바이스, 이름, 종류, 설명 (첫 줄 제목은 있어도 없어도 됨)
export function parseIoCsv(text: string): CsvResult {
  const all = parseCsv(text);
  const warnings: string[] = [];
  const hasHeader = all.length > 0 && HEADER_WORDS.includes(all[0][0].trim().toLowerCase());
  const body = hasHeader ? all.slice(1) : all;
  if (body.length > MAX_ROWS) warnings.push(`${MAX_ROWS}행까지만 가져왔어요.`);
  const rows = body.slice(0, MAX_ROWS).map((c, i) => {
    const kind = (c[2] ?? "").trim();
    const known = IO_KINDS.includes(kind);
    if (kind && !known) warnings.push(`${i + 1}번째 줄: 종류 "${kind}"를 알 수 없어 "기타"로 넣었어요.`);
    return { ...emptyRow(), device: (c[0] ?? "").trim(), name: (c[1] ?? "").trim(), kind: known ? kind : IO_KINDS.includes("기타") ? "기타" : IO_KINDS[0] ?? "", desc: (c[3] ?? "").trim() };
  });
  return { rows, warnings };
}

export function csvTemplate(): string {
  return "\uFEFF디바이스,이름,종류,설명\r\nX0,START_PB,푸시버튼 NO,기동 버튼\r\nX1,STOP_PB,푸시버튼 NC,정지 버튼\r\nY0,MOTOR,모터,모터 접촉기\r\n";
}

export function downloadCsvTemplate() {
  const url = URL.createObjectURL(new Blob([csvTemplate()], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "io_list_template.csv";
  a.click();
  URL.revokeObjectURL(url);
}
