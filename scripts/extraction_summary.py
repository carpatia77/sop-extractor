import glob
import re
import os

WORDS_PER_TOKEN_MULTIPLIER = 1.33  # Claude/OpenAI rule of thumb: ~1 word = 1.33 tokens


def _course_stats(source_dir: str) -> dict:
    """Computes duration/word/token stats for one course directory. Pure
    computation, no printing — returns None if the course has no transcripts
    (skipped, same as the original inline behavior)."""
    srt_files = glob.glob(os.path.join(source_dir, 'transcripts', '*.srt'))
    if not srt_files:
        return None

    course_sec = 0
    input_words = 0
    for f in srt_files:
        try:
            with open(f, encoding='utf-8-sig') as file:
                lines = file.readlines()
                input_words += sum(len(line.split()) for line in lines)
                for line in reversed(lines):
                    m = re.search(r'(\d{2}):(\d{2}):(\d{2}),\d{3}', line)
                    if m:
                        h, mi, s = map(int, m.groups())
                        course_sec += h * 3600 + mi * 60 + s
                        break
        except Exception:
            pass

    output_words = 0
    md_files = glob.glob(os.path.join(source_dir, 'chapters', '*.md')) + [
        os.path.join(source_dir, 'SKILL.md'),
        os.path.join(source_dir, 'sops.md'),
        os.path.join(source_dir, 'first_principles.md'),
        os.path.join(source_dir, 'glossary.md'),
        os.path.join(source_dir, 'coherence_audit.md'),
    ]
    for f in md_files:
        try:
            if os.path.exists(f):
                with open(f, encoding='utf-8-sig') as file:
                    output_words += sum(len(line.split()) for line in file.readlines())
        except Exception:
            pass

    hours = course_sec / 3600
    input_tokens = int(input_words * WORDS_PER_TOKEN_MULTIPLIER)
    output_tokens = int(output_words * WORDS_PER_TOKEN_MULTIPLIER)
    return {
        "course_name": os.path.basename(source_dir),
        "hours": hours,
        "input_words": input_words,
        "output_words": output_words,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def compute_summary(examples_glob: str = 'examples/*/') -> dict:
    """Scans every course directory matching examples_glob and returns
    per-course stats plus totals. Pure computation, no printing — extracted
    so it's testable without capturing stdout."""
    sources = [os.path.dirname(d) for d in glob.glob(examples_glob)]
    courses = []
    for source in sorted(set(sources)):
        stats = _course_stats(source)
        if stats is not None:
            courses.append(stats)

    total_hours = sum(c["hours"] for c in courses)
    total_input_words = sum(c["input_words"] for c in courses)
    total_output_words = sum(c["output_words"] for c in courses)
    return {
        "courses": courses,
        "total_hours": total_hours,
        "total_input_words": total_input_words,
        "total_output_words": total_output_words,
        "total_input_tokens": int(total_input_words * WORDS_PER_TOKEN_MULTIPLIER),
        "total_output_tokens": int(total_output_words * WORDS_PER_TOKEN_MULTIPLIER),
        "grand_total_tokens": int((total_input_words + total_output_words) * WORDS_PER_TOKEN_MULTIPLIER),
    }


def print_summary(examples_glob: str = 'examples/*/'):
    summary = compute_summary(examples_glob)
    print("=== Extraction Summary ===")
    for c in summary["courses"]:
        print(f"\n[{c['course_name']}]")
        print(f"  - Duration: {c['hours']:.2f} hours")
        print(f"  - Input (SRT): ~{c['input_tokens']:,} tokens ({c['input_words']:,} words)")
        print(f"  - Output (MD): ~{c['output_tokens']:,} tokens ({c['output_words']:,} words)")
        print(f"  - Total Context: ~{c['input_tokens'] + c['output_tokens']:,} tokens")

    print("\n=== OVERALL (Courses Only) ===")
    print(f"Total Duration: {summary['total_hours']:.2f} hours")
    print(f"Total Input Tokens: ~{summary['total_input_tokens']:,}")
    print(f"Total Output Tokens: ~{summary['total_output_tokens']:,}")
    print(f"Grand Total Tokens Processed: ~{summary['grand_total_tokens']:,}")


def main():
    print_summary()


if __name__ == '__main__':
    main()
