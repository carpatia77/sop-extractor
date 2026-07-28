#!/usr/bin/env python3
"""Chavruta Engine v2 — robust debate motor with evidence-backed challenges.

Improvements over v1:
  1. Conversation memory — tracks what was discussed, avoids repetition
  2. Evidence-backed challenges — cites specific nodes with evidence_ids
  3. Safety valve — always asks for evidence when uncertain
  4. Depth-aware templates — qualitatively different challenges per level
  5. Semantic guard integration — catches subtle errors
  6. Camada 4 (embeddings) active — paraphrase matching via sf_matcher

Architecture:
  sf_matcher (4 layers) → drift_detector → semantic_guard → depth_tracker → engine_v2
  All stateful, all deterministic, all grounded in graph events.
"""
from __future__ import annotations

import json
import os

try:
    from scripts.chavruta.sf_matcher import find_nodes, find_best_match
    from scripts.chavruta.drift_detector import detect_drift
    from scripts.chavruta.depth_tracker import evaluate_depth, depth_bar
except ImportError:
    from chavruta.sf_matcher import find_nodes, find_best_match
    from chavruta.drift_detector import detect_drift
    from chavruta.depth_tracker import evaluate_depth, depth_bar


# ---------------------------------------------------------------------------
# Evidence-backed challenge templates
# ---------------------------------------------------------------------------

def _cite_evidence(node: dict) -> str:
    """Generate evidence citation for a node."""
    parts = []
    eid = node.get("evidence_id") or node.get("entry_id", "")
    if eid:
        parts.append(f"[{eid}]")
    epistemic = node.get("epistemic_status", "")
    if epistemic:
        parts.append(f"epistemic: {epistemic}")
    locator = node.get("locator", "")
    if locator:
        parts.append(f"fonte: {locator}")
    return " ".join(parts) if parts else ""


def _challenge_with_evidence(node: dict, depth: int, connected: list[dict] | None = None) -> str:
    """Generate a challenge that cites specific evidence."""
    citation = _cite_evidence(node)
    statement = node.get("statement", "")
    term = node.get("term", "")

    if depth == 1:
        return f"O que o autor diz sobre '{term or statement[:40]}'? Mostre o trecho. {citation}"

    if depth == 2:
        return f"Por que o autor afirma isso? Qual é o raciocínio? {citation}"

    if depth == 3:
        disconfirming = node.get("disconfirming_evidence", "")
        if disconfirming:
            return f"Mas e se {disconfirming}? Como você responde a isso? {citation}"
        return f"O que aconteceria se essa premissa estiver errada? {citation}"

    if depth == 4 and connected and len(connected) >= 2:
        n1 = connected[0].get("term") or connected[0].get("name", "")
        n2 = connected[1].get("term") or connected[1].get("name", "")
        return f"Como '{n1}' se conecta com '{n2}'? Qual é a relação? {citation}"

    if depth == 5:
        alt = node.get("strongest_alternative", "")
        if alt:
            return f"O SF registra: {alt}. Você concorda? Por quê? {citation}"
        return f"Há uma perspectiva alternativa que você considerou? {citation}"

    if depth == 6:
        return ("Interessante — isso não está no SF. "
                "Onde exatamente o autor afirma isso? "
                "Precisamos de evidência antes de adicionar ao grafo. "
                f"{citation}")

    if depth == 7:
        return ("Bom — reconhecer o que não se sabe é o nível mais alto. "
                "O que você gostaria de entender melhor? "
                "Podemos buscar na fonte original. "
                f"{citation}")

    return f"Elabore mais sobre: '{term or statement[:50]}'. {citation}"


# ---------------------------------------------------------------------------
# Repetition detection
# ---------------------------------------------------------------------------

def _was_already_challenged(history: list[dict], node_id: str, depth: int) -> bool:
    """Check if this node+depth combination was already challenged."""
    for h in history:
        if h.get("matched_node_id") == node_id and h.get("depth") == depth:
            return True
    return False


# ---------------------------------------------------------------------------
# Chavruta Engine v2
# ---------------------------------------------------------------------------

class ChavrutaEngineV2:
    """Robust debate engine with evidence-backed challenges.

    Improvements over v1:
    - Conversation memory (no repetition)
    - Evidence citation in every challenge
    - Safety valve (always ask for evidence)
    - Semantic guard integration
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
        self.nodes_challenged: set[str] = set()  # Track which nodes were challenged

    def process(self, user_response: str) -> dict:
        """Process a user response through the debate loop.

        Returns dict with drift/depth/challenge info.
        """
        # Step 1: Drift + contradiction + semantic guard
        drift_result = detect_drift(
            user_response, self.sf, self.task_contract,
            evidence_ledger=self.evidence_ledger,
        )

        if drift_result["is_drift"] and not drift_result["is_contradiction"]:
            return self._build_drift_response(drift_result)

        # Step 2: Evaluate depth
        depth_result = evaluate_depth(
            user_response, self.sf, self.task_contract, self.evidence_ledger,
        )

        # Step 3: Find primary matched node (with layer tracking)
        best_node, match_layer = find_best_match(user_response, self.sf)
        # For contradiction challenges, prefer nodes with evidence_id
        if drift_result["is_contradiction"] and best_node and not best_node.get("evidence_id"):
            all_matches = find_nodes(user_response, self.sf)
            for node in all_matches:
                if node.get("evidence_id"):
                    best_node = node
                    match_layer = "substring"  # upgraded via find_nodes
                    break

        # Step 4: Semantic issues — reuse from drift_detector (already ran check_semantic_errors)
        semantic_issues = drift_result.get("semantic_issues", [])

        # Step 5: Generate evidence-backed challenge
        depth = depth_result["depth"]
        challenge = self._generate_challenge(
            user_response, best_node, depth, drift_result, semantic_issues,
        )

        # Step 6: Update state
        self.max_depth_seen = max(self.max_depth_seen, depth)
        node_id = best_node["id"] if best_node else None
        if node_id:
            self.nodes_challenged.add(node_id)

        # Record in history
        self.history.append({
            "response": user_response[:200],
            "depth": depth,
            "is_contradiction": drift_result["is_contradiction"],
            "anchor_used": drift_result["anchor_used"],
            "matched_node_id": node_id,
            "match_layer": match_layer,
            "semantic_issues": [
                {"type": i["type"], "severity": i["severity"]} for i in semantic_issues
            ],
        })

        return {
            "is_drift": False,
            "is_contradiction": drift_result["is_contradiction"],
            "depth": depth,
            "depth_label": depth_result["label"],
            "depth_bar": depth_bar(depth),
            "challenge": challenge,
            "matched_node": best_node,
            "match_layer": match_layer,
            "anchor_used": drift_result["anchor_used"],
            "max_depth_seen": self.max_depth_seen,
            "semantic_issues": semantic_issues,
        }

    def _generate_challenge(
        self,
        user_response: str,
        best_node: dict | None,
        depth: int,
        drift_result: dict,
        semantic_issues: list[dict] | None = None,
    ) -> str:
        """Generate an evidence-backed challenge."""
        # Contradiction — challenge with the principle
        if drift_result["is_contradiction"]:
            if best_node:
                citation = _cite_evidence(best_node)
                return (f"Você está contradizendo: '{best_node.get('statement', '')[:80]}'. "
                        f"Qual é a sua evidência? {citation}")
            return "Qual é a evidência para essa afirmação?"

        # Semantic issues — challenge the specific error (from drift_detector's check_semantic_errors)
        if semantic_issues:
            issue = semantic_issues[0]
            return f"Atenção: {issue['message'][:100]}. Verifique suas fontes."

        # Depth-specific challenge with evidence
        if best_node:
            # Check if this node was already challenged (repetition detection)
            node_id = best_node["id"]
            if _was_already_challenged(self.history, node_id, depth):
                # Already challenged at this depth — escalate or vary
                return f"Já discutimos isso. Vamos aprofundar em outro aspecto de '{best_node.get('term', '')}'?"

            # Find connected nodes for depth 4
            connected = []
            if depth == 4:
                matched = find_nodes(user_response, self.sf)
                matched_ids = {n["id"] for n in matched}
                for edge in self.sf.get("edges", []):
                    if edge["source"] in matched_ids and edge["target"] in matched_ids:
                        for n in matched:
                            if n["id"] in (edge["source"], edge["target"]):
                                connected.append(n)
                        break
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

            return _challenge_with_evidence(best_node, depth, connected)

        # Safety valve — always ask for evidence
        return "Pode elaborar mais? Cite a fonte ou o trecho que sustenta sua afirmação."

    def _build_drift_response(self, drift_result: dict) -> dict:
        """Build response for drift (outside scope)."""
        self.history.append({
            "response": "(drift)",
            "depth": 0,
            "is_contradiction": False,
            "anchor_used": "none",
            "matched_node_id": None,
            "match_layer": "none",
            "semantic_issues": drift_result.get("semantic_issues", []),
        })

        return {
            "is_drift": True,
            "is_contradiction": False,
            "depth": 0,
            "depth_label": "Fora de escopo",
            "depth_bar": "░░░░░░░░░░░░░░░░░░░░ 0/7",
            "challenge": ("Isso parece estar fora do tema. "
                          "Vamos voltar ao que o autor ensina?"),
            "matched_node": None,
            "match_layer": "none",
            "anchor_used": "none",
            "max_depth_seen": self.max_depth_seen,
            "semantic_issues": drift_result.get("semantic_issues", []),
        }

    def get_session_summary(self) -> dict:
        """Get summary of the debate session."""
        if not self.history:
            return {"total_moves": 0, "max_depth": 0, "contradictions": 0}

        depths = [h["depth"] for h in self.history if h["depth"] > 0]
        contradictions = sum(1 for h in self.history if h["is_contradiction"])

        return {
            "total_moves": len(self.history),
            "max_depth": max(depths) if depths else 0,
            "avg_depth": sum(depths) / len(depths) if depths else 0,
            "contradictions": contradictions,
            "nodes_challenged": len(self.nodes_challenged),
            "depth_distribution": {d: depths.count(d) for d in range(1, 8)},
        }

    def save_state(self, path: str) -> None:
        """Save engine state to disk."""
        state = {
            "history": self.history,
            "max_depth_seen": self.max_depth_seen,
            "nodes_challenged": list(self.nodes_challenged),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)

    def load_state(self, path: str) -> None:
        """Load engine state from disk."""
        if not os.path.exists(path):
            return
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
        self.history = state.get("history", [])
        self.max_depth_seen = state.get("max_depth_seen", 0)
        self.nodes_challenged = set(state.get("nodes_challenged", []))
