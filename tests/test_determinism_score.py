import json
from scripts.determinism_score import score_chapter, score_skill

def test_chapter_all_sops():
    text = """
# Chapter 1

## Standard Operating Procedure (SOP)
### SOP: Do X
- Trigger: A
- Steps: 1, 2
### SOP: Do Y
- Trigger: B
- Steps: 3, 4
"""
    result = score_chapter(text)
    assert result["n_sops"] == 2
    assert result["n_heuristics"] == 0
    assert result["determinism_pct"] == 1.0

def test_chapter_all_heuristics():
    text = """
# Chapter 1

## Heuristics (under uncertainty)
- When X, do Y
- When A, do B
- When C, do D
"""
    result = score_chapter(text)
    assert result["n_sops"] == 0
    assert result["n_heuristics"] == 3
    assert result["determinism_pct"] == 0.0

def test_chapter_no_signal():
    text = """
# Chapter 1

## First Principles
- Principle 1

## Anti-patterns
- Anti-pattern 1
"""
    result = score_chapter(text)
    assert result["n_sops"] == 0
    assert result["n_heuristics"] == 0
    assert result["determinism_pct"] is None

def test_aggregation_raw_sum(tmp_path):
    # Setup temp skill dir
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    
    # Chapter 1: 8 SOPs, 0 Heuristics
    ch1 = chapters_dir / "ch01.md"
    ch1.write_text("\n".join(["### SOP: Task"] * 8))
    
    # Chapter 2: 1 SOP, 1 Heuristic
    ch2 = chapters_dir / "ch02.md"
    ch2.write_text("### SOP: Task\n## Heuristics (under uncertainty)\n- Heur1")
    
    result = score_skill(chapters_dir)
    # Total SOPs = 9, Total Heur = 1 -> Pct = 90% (not (100+50)/2)
    assert result["book_determinism_pct"] == 0.9
    assert result["total_sops"] == 9
    assert result["total_heuristics"] == 1
    assert result["chapters_with_procedural_signal"] == 2

def test_idempotence(tmp_path):
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    ch1 = chapters_dir / "ch01.md"
    ch1.write_text("### SOP: Task\n## Heuristics (under uncertainty)\n- Heur1")
    
    result1 = score_skill(chapters_dir)
    result2 = score_skill(chapters_dir)
    
    assert json.dumps(result1) == json.dumps(result2)

def test_regex_false_positives():
    text = """
# Chapter 1

Here is a paragraph that mentions ### SOP: but not as a true heading.
And another line: "### SOP: fake" inside a blockquote.
Wait, our regex only matches `^### SOP:\s*.+$` at the start of a line. 
But what if it's inside a code block? The specification says "pure structural parsing".
If the author writes `### SOP: fake` at the start of a line in a code block, it might get caught.
But let's ensure it doesn't match just "SOP:" in the middle of a sentence.
"""
    result = score_chapter(text)
    assert result["n_sops"] == 0
    
    text_with_real_sop = "### SOP: Real SOP\n- Steps"
    assert score_chapter(text_with_real_sop)["n_sops"] == 1

def test_code_fences_false_positive():
    text = """
# Chapter 1

Some prose.
```markdown
### SOP: Example Task
- This is just an example inside a code block
```
"""
    result = score_chapter(text)
    assert result["n_sops"] == 0

def test_transcript_modules(tmp_path):
    chapters_dir = tmp_path / "chapters"
    chapters_dir.mkdir()
    
    # Transcript modules use mod*.md instead of ch*.md
    mod1 = chapters_dir / "mod01.md"
    mod1.write_text("### SOP: Task 1")
    
    mod2 = chapters_dir / "mod02.md"
    mod2.write_text("## Heuristics (under uncertainty)\n- Heur1\n- Heur2")
    
    result = score_skill(chapters_dir)
    assert result["total_sops"] == 1
    assert result["total_heuristics"] == 2
    assert result["chapters_total"] == 2
    assert result["book_determinism_pct"] == (1 / 3)
