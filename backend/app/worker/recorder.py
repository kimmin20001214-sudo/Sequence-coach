"""FFmpeg로 창을 녹화하고 자막(시나리오 단계 + 안전 고지)을 넣는다."""
import shutil
import subprocess
from pathlib import Path

from .common import StepResult

SAFETY_NOTICE = "설계 초안입니다. 실제 설비 적용 전 자격을 갖춘 사람의 검토가 필요합니다."


def _escape(text: str) -> str:
    for ch, rep in (("\\", "\\\\"), (":", "\\:"), ("'", "\u2019"), ("%", "\\%")):
        text = text.replace(ch, rep)
    return text


def capture_command(window_title: str, out: Path, seconds: int, framerate: int = 30) -> list[str]:
    return [
        "ffmpeg", "-y", "-f", "gdigrab", "-framerate", str(framerate),
        "-i", f"title={window_title}", "-t", str(seconds),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
    ]


def subtitle_command(src: Path, out: Path, steps: list[str], seconds_per_step: float, font: str = "") -> list[str]:
    """단계마다 아래쪽에 자막을 띄우고, 영상 내내 안전 고지를 위쪽에 둔다."""
    font_opt = f"fontfile='{_escape(font)}':" if font else ""
    filters = [f"drawtext={font_opt}text='{_escape(SAFETY_NOTICE)}':fontcolor=yellow:fontsize=22:x=20:y=20:box=1:boxcolor=black@0.6"]
    for i, step in enumerate(steps):
        start, end = i * seconds_per_step, (i + 1) * seconds_per_step
        filters.append(
            f"drawtext={font_opt}text='{_escape(f'{i + 1}. {step}')}':fontcolor=white:fontsize=26:x=20:y=h-60:"
            f"box=1:boxcolor=black@0.6:enable='between(t,{start},{end})'"
        )
    return ["ffmpeg", "-y", "-i", str(src), "-vf", ",".join(filters), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)]


def record(window_title: str, out: Path, seconds: int) -> StepResult:
    if not shutil.which("ffmpeg"):
        return StepResult("not_run", "FFmpeg가 설치되어 있지 않아요.")
    out.parent.mkdir(parents=True, exist_ok=True)
    p = subprocess.run(capture_command(window_title, out, seconds), capture_output=True, text=True, timeout=seconds + 60)
    if p.returncode != 0 or not out.exists():
        return StepResult("failed", f"FFmpeg 종료 코드 {p.returncode}: {p.stderr[-300:]}")
    return StepResult("completed", path=str(out))


def add_subtitles(src: Path, out: Path, steps: list[str], seconds_per_step: float, font: str = "") -> StepResult:
    if not shutil.which("ffmpeg"):
        return StepResult("not_run", "FFmpeg가 설치되어 있지 않아요.")
    p = subprocess.run(subtitle_command(src, out, steps, seconds_per_step, font), capture_output=True, text=True, timeout=600)
    if p.returncode != 0 or not out.exists():
        return StepResult("failed", f"FFmpeg 종료 코드 {p.returncode}: {p.stderr[-300:]}")
    return StepResult("completed", path=str(out))
