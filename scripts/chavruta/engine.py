#!/usr/bin/env python3
"""Chavruta Engine — debate motor for /teach mode.

Orchestrates the Socratic debate loop:
  1. User makes a claim
  2. Engine validates against SF (drift + contradiction check)
  3. Engine evaluates depth (1-7)
  4. Engine generates challenge based on depth level
  5. Engine updates SF if new insight emerged

The Semantic Field is the ground truth (Talmud). The refutation chain
provides stress-test data. The depth tracker measures progress.

Architecture:
  - sf_matcher: finds nodes in SF
  - drift_detector: blocks drift + detects contradictions
  - depth_tracker: measures debate depth
  - evidence_ledger: provides evidence_text for anchor #3
"""
from __future__ import annotations

try:
    from scripts.verify_concept_presence import salient_terms  # noqa: F401
    from scripts.chavruta.sf_matcher import find_nodes, find_best_match
    from scripts.chavruta.drift_detector import detect_drift
    from scripts.chavruta.depth_tracker import evaluate_depth, depth_bar
except ImportError:
    from verify_concept_presence import salient_terms  # noqa: F401
    from chavruta.sf_matcher import find_nodes, find_best_match
    from chavruta.drift_detector import detect_drift
    from chavruta.depth_tracker import evaluate_depth, depth_bar


# ---------------------------------------------------------------------------
# Challenge generation (depth-specific)
# ---------------------------------------------------------------------------

def _challenge_depth_1(node: dict) -> str:
    """Depth 1: ask what the author actually says."""
    statement = node.get("statement", "")
    return f"O que exatamente o autor diz sobre isso? Mostre o trecho. ({statement[:80]}...)"


def _challenge_depth_2(node: dict) -> str:
    """Depth 2: ask why — what's the reasoning."""
    return "Por que o autor afirma isso? Qual é o raciocínio por trás?"


def _challenge_depth_3(node: dict) -> str:
    """Depth 3: present the disconfirming evidence."""
    disconfirming = node.get("disconfirming_evidence", "")
    if disconfirming:
        return f"Mas e se {disconfirming}? Como você responde a isso?"
    return "O que aconteceria se essa premissa estiver errada?"


def _challenge_depth_4(node: dict, connected: list[dict]) -> str:
    """Depth 4: ask how concepts connect."""
    if len(connected) < 2:
        return "Você mencionou conceitos conectados. Como eles se relacionam?"
    names = [n.get("term") or n.get("name") or n.get("statement", "")[:40] for n in connected[:2]]
    return f"Como '{names[0]}' se conecta com '{names[1]}'? Qual é a relação?"


def _challenge_depth_5(node: dict) -> str:
    """Depth 5: present the strongest alternative."""
    alt = node.get("strongest_alternative", "")
    if alt:
        return f"O SF registra uma alternativa: {alt}. Você concorda? Por quê?"
    return "Há uma perspectiva alternativa que você considerou?"


def _challenge_depth_6(node: dict) -> str:
    """Depth 6: validate the new term's grounding."""
    return ("Interessante — isso não está no SF. "
            "Onde exatamente o autor afirma isso? "
            "Precisamos de evidência antes de adicionar ao grafo.")


def _challenge_depth_7(node: dict) -> str:
    """Depth 7: acknowledge and deepen meta-cognition."""
    return ("Bom — reconhecer o que não se sabe é o nível mais alto. "
            "O que você gostaria de entender melhor? "
            "Podemos buscar na fonte original.")


CHALLENGE_FNS = {
    1: _challenge_depth_1,
    2: _challenge_depth_2,
    3: _challenge_depth_3,
    4: _challenge_depth_4,
    5: _challenge_depth_5,
    6: _challenge_depth_6,
    7: _challenge_depth_7,
}


# ---------------------------------------------------------------------------
# Chavruta Engine
# ---------------------------------------------------------------------------

class ChavrutaEngine:
    """Stateful debate engine for /teach mode.

    Usage:
        engine = ChavrutaEngine(sf, task_contract, evidence_ledger)
        result = engine.process("Volatility drag compounds against you")
        print(result["challenge"])
        print(result["depth_bar"])
    """

    def __init__(
        self,
        sf: dict,
        task_contract: dict | None = None,
        evidence_ledger: dict | None = None,
    ):
        self.sf = sf
        self.task_contract = task_contract
        self.evidence_ledger = evidence_ledger
        self.history: list[dict] = []
        self.max_depth_seen: int = 0

    def process(self, user_response: str) -> dict:
        """Process a user response through the debate loop.

        Returns dict with:
            - is_drift: bool
            - is_contradiction: bool
            - depth: int (1-7)
            - depth_label: str (chess analogy)
            - depth_bar: str (visual bar)
            - challenge: str (next challenge question)
            - matched_node: dict | None (primary node matched)
            - anchor_used: str
            - max_depth_seen: int (all-time high)
        """
        # Step 1: Drift + contradiction check
        drift_result = detect_drift(
            user_response, self.sf, self.task_contract,
        )

        if drift_result["is_drift"] and not drift_result["is_contradiction"]:
            # Pure drift — outside scope
            return {
                "is_drift": True,
                "is_contradiction": False,
                "depth": 0,
                "depth_label": "Fora de escopo",
                "depth_bar": "░░░░░░░░░░░░░░░░░░░░ 0/7",
                "challenge": ("Isso parece estar fora do tema. "
                              "Vamos voltar ao que o autor ensina?"),
                "matched_node": None,
                "anchor_used": drift_result["anchor_used"],
                "max_depth_seen": self.max_depth_seen,
            }

        # Step 2: Evaluate depth
        depth_result = evaluate_depth(
            user_response, self.sf, self.task_contract, self.evidence_ledger,
        )

        # Step 3: Find primary matched node
        best_node, _layer = find_best_match(user_response, self.sf)

        # Step 4: Generate challenge
        depth = depth_result["depth"]
        if drift_result["is_contradiction"]:
            # Contradiction — challenge with the principle
            if best_node:
                challenge = (f"Você está contradizendo: '{best_node.get('statement', '')[:80]}'. "
                             f"Qual é a sua evidência? O SF registra epistemic_status: "
                             f"{best_node.get('epistemic_status', '?')}")
            else:
                challenge = "Qual é a evidência para essa afirmação?"
        elif best_node and depth in CHALLENGE_FNS:
            # Normal depth-specific challenge
            connected = []
            if depth == 4:
                # Find connected nodes for depth 4
                matched = find_nodes(user_response, self.sf)
                matched_ids = {n["id"] for n in matched}
                # Case 1: both matched nodes are connected to each other
                for edge in self.sf.get("edges", []):
                    if edge["source"] in matched_ids and edge["target"] in matched_ids:
                        # Both endpoints matched — they ARE the connected pair
                        for n in matched:
                            if n["id"] in (edge["source"], edge["target"]):
                                connected.append(n)
                        break
                # Case 2: matched nodes have neighbors not in matched set
                if len(connected) < 2:
                    for edge in self.sf.get("edges", []):
                        if edge["source"] in matched_ids:
                            for n in self.sf.get("nodes", []):
                                if n["id"] == edge["target"] and n["id"] not in matched_ids:
                                    connected.append(n)
                        elif edge["target"] in matched_ids:
                            for n in self.sf.get("nodes", []):
                                if n["id"] == edge["source"] and n["id"] not in matched_ids:
                                    connected.append(n)
            challenge = CHALLENGE_FNS[depth](best_node) if depth != 4 else CHALLENGE_FNS[depth](best_node, connected)
        else:
            challenge = "Pode elaborar mais sobre o que o autor ensina?"

        # Step 5: Update max depth
        self.max_depth_seen = max(self.max_depth_seen, depth)

        # Record in history
        self.history.append({
            "response": user_response[:200],
            "depth": depth,
            "is_contradiction": drift_result["is_contradiction"],
            "anchor_used": drift_result["anchor_used"],
        })

        return {
            "is_drift": False,
            "is_contradiction": drift_result["is_contradiction"],
            "depth": depth,
            "depth_label": depth_result["label"],
            "depth_bar": depth_bar(depth),
            "challenge": challenge,
            "matched_node": best_node,
            "anchor_used": drift_result["anchor_used"],
            "max_depth_seen": self.max_depth_seen,
        }

    def get_session_summary(self) -> dict:
        """Get summary of the debate session."""
        if not self.history:
            return {"total_moves": 0, "max_depth": 0, "contradictions": 0}

        depths = [h["depth"] for h in self.history]
        contradictions = sum(1 for h in self.history if h["is_contradiction"])

        return {
            "total_moves": len(self.history),
            "max_depth": max(depths),
            "avg_depth": sum(depths) / len(depths),
            "contradictions": contradictions,
            "depth_distribution": {d: depths.count(d) for d in range(1, 8)},
        }
