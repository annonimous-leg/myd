"""
SovereignShell: Gobernanza descentralizada con peer prediction.
"""

import hashlib
import time
import json
from dataclasses import dataclass
from enum import Enum
from typing import List, Dict
from collections import defaultdict

class ProposalType(Enum):
    UPDATE_PARAM = "update_param"
    ENABLE_FEATURE = "enable_feature"
    DISABLE_FEATURE = "disable_feature"
    UPGRADE_HASH = "upgrade_hash"
    SLASH_NODE = "slash_node"
    RESOLUTION_MARKET = "resolution_market"

class VoteType(Enum):
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"

@dataclass
class Proposal:
    id: str
    proposer: str
    type: ProposalType
    payload: dict
    timestamp: float
    voting_starts: float
    voting_ends: float
    timelock_ends: float
    votes: Dict[str, VoteType]
    status: str

    @property
    def hash(self) -> str:
        payload = f"{self.proposer}|{self.type.value}|{self.timestamp}|{json.dumps(self.payload, sort_keys=True)}"
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

class SovereignShell:
    SUPERMAJORITY = 0.80
    QUORUM = 0.40
    HEAVY_NODE_THRESHOLD = 0.67
    VETO_DELAY = 172800

    def __init__(self, peer_engine, honeypot_engine, sprt_engine):
        self.peer_engine = peer_engine
        self.honeypot_engine = honeypot_engine
        self.sprt_engine = sprt_engine
        self.proposals: Dict[str, Proposal] = {}
        self.nodes: Dict[str, dict] = {}
        self.heavy_nodes: List[str] = []
        self.executed_upgrades: List[str] = []
        # Registrar sprt_engine como proposer del sistema
        self.nodes["sprt_engine"] = {
            'type': 'system', 'stake': 0.0, 'reputation': 100.0,
            'proposals_created': 0, 'proposals_voted': 0, 'slash_count': 0
        }

    def register_node(self, node_id, node_type, stake=0):
        score = self.peer_engine.get_node_score(node_id)
        if node_type == 'oracle' and (score['n_verified'] < 30 or score['reliability'] < 0.99):
            raise ValueError(f"Nodo {node_id} no califica como oráculo")
        self.nodes[node_id] = {
            'type': node_type, 'stake': stake, 'reputation': 100.0,
            'joined_at': time.time(), 'votes_cast': 0, 'proposals_created': 0
        }
        if node_type == "heavy":
            self.heavy_nodes.append(node_id)

    def evaluate_oracle(self, node_id):
        score = self.peer_engine.get_node_score(node_id)
        reliability = score.get('reliability', 0.0)
        n_verified = score.get('n_verified', 0)
        if reliability < 0.99 or n_verified < 30:
            return False, f"reliability={reliability:.3f}, verif={n_verified}"
        weight = score.get('stake', 0.0) * reliability
        return True, weight

    def auto_slash_proposal(self, node_id):
        status = self.sprt_engine.get_status(node_id)
        if status['decision'] == 'slash':
            return self.create_proposal(
                "sprt_engine", ProposalType.SLASH_NODE,
                {'node_id': node_id, 'severity': 'critical',
                 'evidence': status, 'mechanism': 'sprt_peer_prediction'}
            )
        return None

    def create_proposal(self, proposer, ptype, payload):
        if proposer not in self.nodes:
            raise ValueError("Node not registered")
        now = time.time()
        proposal = Proposal("", proposer, ptype, payload, now,
                           now + 259200, now + 864000, now + 1036800, {}, "pending")
        proposal.id = proposal.hash
        self.proposals[proposal.id] = proposal
        self.nodes[proposer]['proposals_created'] += 1
        return proposal.id

    def cast_vote(self, node_id, proposal_id, vote):
        if node_id not in self.nodes:
            raise ValueError("Node not registered")
        proposal = self.proposals.get(proposal_id)
        if not proposal:
            raise ValueError("Proposal not found")
        if time.time() < proposal.voting_starts:
            raise ValueError("Voting not started")
        if time.time() > proposal.voting_ends:
            raise ValueError("Voting ended")

        node = self.nodes[node_id]
        weight = self._calculate_vote_weight(node)
        proposal.votes[node_id] = {'vote': vote, 'weight': weight, 'timestamp': time.time()}
        node['votes_cast'] += 1
        self._check_consensus(proposal_id)

    def _calculate_vote_weight(self, node):
        type_mult = {'light': 1, 'full': 5, 'oracle': 10, 'heavy': 20}
        base = type_mult.get(node['type'], 1)
        stake_factor = 1 + (node['stake'] / 10000)
        rep_factor = node['reputation'] / 100
        return base * stake_factor * rep_factor

    def _check_consensus(self, proposal_id):
        proposal = self.proposals[proposal_id]
        votes = proposal.votes
        total_weight = sum(v['weight'] for v in votes.values())
        yes_weight = sum(v['weight'] for v in votes.values() if v['vote'] == VoteType.YES)
        no_weight = sum(v['weight'] for v in votes.values() if v['vote'] == VoteType.NO)
        total_possible = sum(self._calculate_vote_weight(n) for n in self.nodes.values())
        participation = total_weight / total_possible if total_possible > 0 else 0
        if participation < self.QUORUM:
            return
        if yes_weight / total_weight >= self.SUPERMAJORITY:
            proposal.status = "passed"
        elif no_weight / total_weight >= self.SUPERMAJORITY:
            proposal.status = "rejected"

    def execute_proposal(self, proposal_id):
        proposal = self.proposals[proposal_id]
        if proposal.status != "passed":
            raise ValueError("Proposal not passed")
        if time.time() < proposal.timelock_ends:
            raise ValueError("Timelock not expired")
        if proposal.type == ProposalType.SLASH_NODE:
            self._execute_slash(proposal.payload)
        elif proposal.type == ProposalType.UPGRADE_HASH:
            self._execute_upgrade(proposal.payload)
        proposal.status = "executed"
        self.executed_upgrades.append(proposal_id)

    def _execute_slash(self, payload):
        node_id = payload['node_id']
        severity = payload.get('severity', 'minor')
        penalties = {'minor': 10, 'major': 50, 'critical': 100}
        penalty = penalties.get(severity, 10)
        self.nodes[node_id]['reputation'] -= penalty
        if self.nodes[node_id]['reputation'] <= 0:
            del self.nodes[node_id]
            if node_id in self.heavy_nodes:
                self.heavy_nodes.remove(node_id)

    def _execute_upgrade(self, payload):
        print(f"Upgrading to {payload['version']} with hash {payload['sha256']}")
