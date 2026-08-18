"""Vidorq helper: word-level transcription with local faster-whisper.

Usage:
    python transcribe.py <video_path> <out_dir> [language]

Writes:
    <out_dir>/transcript.json   - segments with word-level timestamps
    <out_dir>/takes_packed.md   - compact phrase view for LLM reasoning

This is the slowest step in the whole program, and it is the first one, so it is
also the one the user sits and watches. Two things make it bearable:

  the graphics card   asked for first and fallen back from silently, because a
                      machine without CUDA libraries must still work
  batching            faster-whisper cuts the audio at the silences and runs
                      several pieces at once instead of one after another

Both are attempts, not assumptions: a missing cuDNN, a card busy with Resolve or
an older faster-whisper all end up on the CPU path, which is where this started.
Progress goes to stdout as PROGRESO lines so the engine can show a real bar
instead of a number that never moves.
"""
import json
import os
import sys
import time
from pathlib import Path


def _cuda_on_path():
    """Put the pip-installed CUDA libraries where Windows will actually look.

    `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12` drops the DLLs under
    site-packages/nvidia/<lib>/bin, which is on no search path at all, so
    ctranslate2 reports "cublas64_12.dll is not found" on a machine where the
    file is sitting right there. os.add_dll_directory is NOT enough: it only
    covers loads that go through Python's own loader, and ctranslate2 asks
    Windows directly. PATH is what that reads, and it has to be set BEFORE
    faster_whisper is imported, which is why this runs at the top of the module
    and not inside a function.
    """
    if os.name != "nt":
        return []
    added = []
    for base in sys.path:
        root = os.path.join(base, "nvidia")
        if not os.path.isdir(root):
            continue
        for lib in sorted(os.listdir(root)):
            binv = os.path.join(root, lib, "bin")
            if os.path.isdir(binv):
                os.environ["PATH"] = binv + os.pathsep + os.environ.get("PATH", "")
                try:
                    os.add_dll_directory(binv)
                except OSError:
                    pass
                added.append(lib)
        if added:
            break
    return added


CUDA_DLLS = _cuda_on_path()

# One model per engine, because the trade is not the same on each. Measured on
# the same ten minute video, transcription time only, model already downloaded:
#
#   large-v3-turbo  cuda   23.3 s   98 phrases, 1450 words   <- the GPU one
#   small           cuda   ~34 s   105 phrases
#   medium          cuda   49.0 s   99 phrases, 1433 words
#   small           cpu    ~16 min                            <- the CPU one
#
# turbo is the surprise and the whole reason for this: it is FASTER than small
# and far more accurate, so on a card there is no argument for the small one.
# On a CPU it would be unbearable, so that path keeps small. What is being
# maximised here is quality per second, not quality and not seconds.
GPU_MODEL = "large-v3-turbo"
CPU_MODEL = "small"
# Batching is OFF, and that is a decision, not an oversight. It is faster, and
# on the same 40 second clip it returned TWO phrases where the plain pass
# returns ten: it glues speech across the silences instead of breaking on them.
# Vidorq cuts on phrase boundaries and the director reads the phrase list, so
# coarser phrases means coarser cuts and less for the model to reason about.
# Speed that costs the edit is not speed. Set it above zero to turn it back on.
BATCH = 0


def probe_duration(path: str) -> float:
    import av

    with av.open(path) as container:
        return float(container.duration) / 1_000_000 if container.duration else 0.0


def cpu_model():
    """The engine that always works. Sixteen threads instead of the default four."""
    import os
    from faster_whisper import WhisperModel
    threads = max(4, (os.cpu_count() or 4))
    return (WhisperModel(CPU_MODEL, device="cpu", compute_type="int8",
                         cpu_threads=threads),
            "%s int8 cpu (%d hilos)" % (CPU_MODEL, threads))


def gpu_model():
    """The card, or None. Building the model is NOT proof that it works.

    Measured trap: WhisperModel(device="cuda") builds happily on a machine that
    has the driver but not the CUDA maths libraries, and then dies in the middle
    of the first transcription with "cublas64_12.dll is not found". Loading it
    is not a test, so the caller keeps a way back and the real check is the first
    piece of audio going through it.
    """
    from faster_whisper import WhisperModel
    for compute in ("float16", "int8_float16"):
        try:
            return (WhisperModel(GPU_MODEL, device="cuda", compute_type=compute),
                    "%s %s cuda" % (GPU_MODEL, compute))
        except Exception:
            continue
    return None, ""


def transcriber(model):
    """The batched pipeline when this version has it, the plain model otherwise."""
    if BATCH <= 0:
        return model, False
    try:
        from faster_whisper import BatchedInferencePipeline
        return BatchedInferencePipeline(model=model), True
    except Exception:
        return model, False


def run(model, video, language, dur, how):
    """One full pass. Raises if the engine cannot finish, so a caller can retry."""
    print("CARGANDO_MODELO: %s" % how, flush=True)
    engine, batched = transcriber(model)
    print("MODO: %s" % ("por lotes" if batched else "seguido"), flush=True)
    opts = dict(language=language, word_timestamps=True, vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 400})
    if batched:
        opts["batch_size"] = BATCH
    segments, info = engine.transcribe(video, **opts)

    seg_list, lines = [], []
    for seg in segments:
        words = [{"w": w.word, "s": round(w.start, 2), "e": round(w.end, 2)}
                 for w in (seg.words or [])]
        seg_list.append({"start": round(seg.start, 2), "end": round(seg.end, 2),
                         "text": seg.text.strip(), "words": words})
        lines.append(f"[{seg.start:07.2f}-{seg.end:07.2f}] {seg.text.strip()}")
        # Every few phrases, not every twenty five: on a ten minute video that
        # was four updates in as many minutes, which reads as a frozen program.
        if len(seg_list) % 5 == 0:
            print(f"PROGRESO: {seg.end:.0f}/{dur:.0f}s", flush=True)
    return seg_list, lines, info


def main() -> None:
    video = sys.argv[1]
    out_dir = Path(sys.argv[2])
    language = sys.argv[3] if len(sys.argv) > 3 else "es"
    out_dir.mkdir(parents=True, exist_ok=True)

    dur = probe_duration(video)
    print(f"DURACION_SEGUNDOS: {dur:.1f}", flush=True)
    if CUDA_DLLS:
        print("CUDA_DLLS: %s" % ", ".join(CUDA_DLLS), flush=True)

    t0 = time.time()
    seg_list, lines, info = None, None, None
    model, how = gpu_model()
    if model:
        try:
            seg_list, lines, info = run(model, video, language, dur, how)
        except Exception as e:
            # The card was there and could not finish. Say so once, in one line,
            # and carry on: the user asked for a transcript, not for a lecture
            # about CUDA.
            print("SIN_GPU: %s" % str(e)[:140], flush=True)
            seg_list = None
    if seg_list is None:
        model, how = cpu_model()
        seg_list, lines, info = run(model, video, language, dur, how)

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
