import type { Config, Meta } from "./spec";
import type { ValidationResult } from "./validate";

const BASE = "/api";

export class ApiError extends Error {
  validation?: ValidationResult;
  constructor(message: string, validation?: ValidationResult) {
    super(message);
    this.validation = validation;
  }
}

export async function fetchMeta(): Promise<Meta> {
  let r: Response;
  try {
    r = await fetch(`${BASE}/meta`);
  } catch {
    throw new ApiError("서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인해 주세요.");
  }
  if (!r.ok) throw new ApiError(`기준 데이터를 불러오지 못했어요. (${r.status})`);
  return r.json();
}

export interface TemplatePayload {
  config: Partial<Config>;
  conditions: { text: string; must_pass: boolean }[];
}

export interface Template {
  id: string;
  name: string;
  builtin: boolean;
  payload: TemplatePayload;
}

async function call(path: string, init?: RequestInit): Promise<Response> {
  let r: Response;
  try {
    r = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError("서버에 연결할 수 없어요. 백엔드가 실행 중인지 확인해 주세요.");
  }
  if (!r.ok) throw new ApiError(`요청에 실패했어요. (${r.status})`);
  return r;
}

export const fetchTemplates = async (): Promise<Template[]> => (await call("/templates")).json();

export const saveTemplate = async (name: string, payload: TemplatePayload): Promise<Template> =>
  (await call("/templates", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, payload }),
  })).json();

export const deleteTemplate = async (id: string): Promise<void> => {
  await call(`/templates/${id}`, { method: "DELETE" });
};

export interface SavedProject {
  id: string;
  status: string;
  [key: string]: unknown;
}

export async function saveProject(body: object): Promise<SavedProject> {
  let r: Response;
  try {
    r = await fetch(`${BASE}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new ApiError("서버에 연결할 수 없어요. 잠시 후 다시 시도해 주세요.");
  }
  if (r.status === 422) {
    const data = await r.json();
    if (data.fields && data.io) {
      throw new ApiError("서버 검증에서 오류가 발견됐어요.", { fields: data.fields, io: data.io });
    }
  }
  if (!r.ok) throw new ApiError(`저장에 실패했어요. (${r.status})`);
  return r.json();
}
