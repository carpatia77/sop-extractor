import glob
import re
import os

def main():
    # Caminhos agnósticos de SO (funcionam em Windows e Linux)
    sources = [os.path.dirname(d) for d in glob.glob('examples/*/')]
    print("=== Extraction Summary ===")
    
    total_hours = 0
    total_input_words = 0
    total_output_words = 0

    # Usando set para garantir unicidade das pastas
    for source in sorted(set(sources)):
        # Verifica se o curso tem transcripts
        srt_files = glob.glob(os.path.join(source, 'transcripts', '*.srt'))
        if not srt_files:
            continue
            
        course_name = os.path.basename(source)
        
        # 1. Calcular Duração e Palavras de Input (Transcrições)
        course_sec = 0
        input_words = 0
        for f in srt_files:
            try:
                with open(f, encoding='utf-8-sig') as file:
                    lines = file.readlines()
                    input_words += sum(len(line.split()) for line in lines)
                    # Encontrar a última linha com timestamp
                    for line in reversed(lines):
                        m = re.search(r'(\d{2}):(\d{2}):(\d{2}),\d{3}', line)
                        if m:
                            h, m, s = map(int, m.groups())
                            course_sec += h * 3600 + m * 60 + s
                            break
            except Exception:
                pass
                
        # 2. Calcular Palavras de Output (Markdown Gerado)
        output_words = 0
        md_files = glob.glob(os.path.join(source, 'chapters', '*.md')) + [
            os.path.join(source, 'SKILL.md'),
            os.path.join(source, 'sops.md'),
            os.path.join(source, 'first_principles.md'),
            os.path.join(source, 'glossary.md'),
            os.path.join(source, 'coherence_audit.md')
        ]
        
        for f in md_files:
            try:
                if os.path.exists(f):
                    with open(f, encoding='utf-8-sig') as file:
                        output_words += sum(len(line.split()) for line in file.readlines())
            except Exception:
                pass
                
        hours = course_sec / 3600
        total_hours += hours
        total_input_words += input_words
        total_output_words += output_words
        
        # Regra do Claude/OpenAI: ~1 palavra = 1.33 tokens
        input_tokens = int(input_words * 1.33)
        output_tokens = int(output_words * 1.33)
        
        print(f"\n[{course_name}]")
        print(f"  - Duration: {hours:.2f} hours")
        print(f"  - Input (SRT): ~{input_tokens:,} tokens ({input_words:,} words)")
        print(f"  - Output (MD): ~{output_tokens:,} tokens ({output_words:,} words)")
        print(f"  - Total Context: ~{input_tokens + output_tokens:,} tokens")

    print(f"\n=== OVERALL (Courses Only) ===")
    print(f"Total Duration: {total_hours:.2f} hours")
    print(f"Total Input Tokens: ~{int(total_input_words * 1.33):,}")
    print(f"Total Output Tokens: ~{int(total_output_words * 1.33):,}")
    print(f"Grand Total Tokens Processed: ~{int((total_input_words + total_output_words) * 1.33):,}")

if __name__ == '__main__':
    main()
