import { useEffect, useState } from "react";
import { fetchTemplates, saveTemplate, deleteTemplate, type Template, type TemplatePayload } from "./api";
import { Card } from "./ui";

interface Props {
  current: () => TemplatePayload;
  onLoad: (p: TemplatePayload) => void;
}

export default function TemplatesCard({ current, onLoad }: Props) {
  const [list, setList] = useState<Template[]>([]);
  const [sel, setSel] = useState("");
  const [name, setName] = useState("");
  const [msg, setMsg] = useState<{ text: string; err?: boolean } | null>(null);

  const refresh = () => fetchTemplates().then(setList).catch((e: Error) => setMsg({ text: e.message, err: true }));
  useEffect(() => { refresh(); }, []);

  const picked = list.find((t) => t.id === sel);

  const load = () => {
    if (!picked) return;
    onLoad(picked.payload);
    setMsg({ text: `"${picked.name}" 템플릿을 불러왔어요. 내용을 설비에 맞게 고쳐 주세요.` });
  };

  const save = async () => {
    if (!name.trim()) return setMsg({ text: "템플릿 이름을 입력해 주세요.", err: true });
    try {
      const t = await saveTemplate(name.trim(), current());
      setName("");
      setSel(t.id);
      setMsg({ text: `"${t.name}" 템플릿으로 저장했어요.` });
      await refresh();
    } catch (e) {
      setMsg({ text: (e as Error).message, err: true });
    }
  };

  const remove = async () => {
    if (!picked || picked.builtin || !window.confirm(`"${picked.name}" 템플릿을 삭제할까요?`)) return;
    try {
      await deleteTemplate(picked.id);
      setSel("");
      setMsg({ text: "삭제했어요." });
      await refresh();
    } catch (e) {
      setMsg({ text: (e as Error).message, err: true });
    }
  };

  return (
    <Card title="설비 템플릿" desc="비슷한 설비의 설정을 불러와 시작하거나, 지금 입력한 내용을 템플릿으로 저장해 다음에 다시 써요.">
      <div className="tpl-row">
        <select aria-label="템플릿 선택" value={sel} onChange={(e) => setSel(e.target.value)}>
          <option value="">템플릿을 선택하세요</option>
          {list.map((t) => <option key={t.id} value={t.id}>{t.builtin ? "[기본] " : ""}{t.name}</option>)}
        </select>
        <button type="button" className="btn ghost" disabled={!picked} onClick={load}>불러오기</button>
        <button type="button" className="btn ghost" disabled={!picked || picked.builtin} onClick={remove}>삭제</button>
      </div>
      <div className="tpl-row">
        <input aria-label="새 템플릿 이름" placeholder="현재 입력을 저장할 이름 (예: 1호기 포장 라인)" maxLength={40} value={name} onChange={(e) => setName(e.target.value)} />
        <button type="button" className="btn ghost" onClick={save}>현재 입력 저장</button>
      </div>
      {msg && <div className={"banner " + (msg.err ? "err" : "ok")} role="status">{msg.text}</div>}
    </Card>
  );
}
