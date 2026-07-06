"""Vidorq helper: word-level transcription with local faster-whisper.

Usage:
    python transcribe.py <video_path> <out_dir> [language]

Writes:
    <out_dir>/transcript.json   - segments with word-level timestamps
    <out_dir>/takes_packed.md   - compact phrase view for LLM reasoning
"""
import json
import sys
import time
from pathlib import Path


def probe_duration(path: str) -> float:
    import av

    with av.open(path) as container:
        return float(container.duration) / 1_000_000 if container.duration else 0.0


def main() -> None:
    video = sys.argv[1]
    out_dir = Path(sys.argv[2])
    language = sys.argv[3] if len(sys.argv) > 3 else "es"
    out_dir.mkdir(parents=True, exist_ok=True)

    dur = probe_duration(video)
    print(f"DURACION_SEGUNDOS: {dur:.1f}", flush=True)

    from faster_whisper import WhisperModel

    print("CARGANDO_MODELO: small int8 cpu", flush=True)
    model = WhisperModel("small", device="cpu", compute_type="int8")

    t0 = time.time()
    segments, info = model.transcribe(
        video,
        language=language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
    )

    seg_list = []
    lines = []
    for seg in segments:
        words = [
            {"w": w.word, "s": round(w.start, 2), "e": round(w.end, 2)}
            for w in (seg.words or [])
        ]
        seg_list.append(
            {
                "start": round(seg.start, 2),
                "end": round(seg.end, 2),
                "text": seg.text.strip(),
                "words": words,
            }
        )
        lines.append(f"[{seg.start:07.2f}-{seg.end:07.2f}] {seg.text.strip()}")
        if len(seg_list) % 25 == 0:
            print(f"PROGRESO: {seg.end:.0f}/{dur:.0f}s", flush=True)

    (out_dir / "transcript.json").write_text(
        json.dumps(
            {"video": video, "duration": dur, "language": info.language, "segments": seg_list},
            ensure_ascii=False,
            indent=1,
        ),
        encoding="utf-8",
    )
    header = (
        f"# Transcripcion empaquetada\n\nVideo: {video}\n"
        f"Duracion: {dur:.1f}s | Frases: {len(seg_list)} | Idioma: {info.language}\n\n"
    )
    (out_dir / "takes_packed.md").write_text(header + "\n".join(lines), encoding="utf-8")
    print(f"COMPLETADO: {len(seg_list)} frases en {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
