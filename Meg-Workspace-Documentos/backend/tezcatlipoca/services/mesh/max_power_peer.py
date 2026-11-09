"""
Motor de peer prediction de máxima potencia.
Combina Output Agreement, BTS, verificación parcial, slashing y DP.
"""

import numpy as np
from scipy.stats import binom
from collections import defaultdict
import time
from typing import Dict, List, Tuple, Optional

class MaxPowerPeerEngine:
    def __init__(self, epsilon_dp=1.0, stake_amount=1000, 
                 verification_rate=0.02, burn_in=50):
        self.epsilon_dp = epsilon_dp
        self.stake_amount = stake_amount
        self.verification_rate = verification_rate
        self.burn_in = burn_in

        self.nodes = {}
        self.reports_history = defaultdict(list)
        self.prob_reports = defaultdict(list)
        self.verified_tasks = set()
        self.ground_truth = {}
        self.verif_stats = defaultdict(lambda: {'correct': 0, 'total': 0})
        self.slash_log = []

    def register_node(self, node_id, node_type='peer', stake=None):
        self.nodes[node_id] = {
            'type': node_type,
            'stake': stake if stake is not None else self.stake_amount,
            'status': 'active',
            'banned': False,
            'mean_payment': 0.5,
            'n_tasks': 0
        }

    def submit_task(self, task_id, ground_truth=None):
        if ground_truth is not None:
            self.verified_tasks.add(task_id)
            self.ground_truth[task_id] = ground_truth
        elif np.random.rand() < self.verification_rate:
            self.verified_tasks.add(task_id)

    def submit_report(self, node_id, task_id, report_binary, 
                      report_prob=None, report_meta=None):
        if node_id not in self.nodes or self.nodes[node_id]['banned']:
            return {'payment': 0, 'status': 'rejected'}

        node = self.nodes[node_id]
        n_tasks = node['n_tasks']

        # Output Agreement
        if n_tasks < self.burn_in:
            oa_payment = 0.5
        else:
            peers = [nid for nid in self.nodes if nid != node_id 
                     and not self.nodes[nid]['banned']]
            if not peers:
                oa_payment = 0.5
            else:
                peer_id = np.random.choice(peers)
                peer_history = [r for tid, r, _ in self.reports_history[peer_id] 
                               if tid != task_id]
                if peer_history:
                    oa_payment = sum(1 for r in peer_history if r == report_binary) / len(peer_history)
                else:
                    oa_payment = 0.5
            oa_payment += np.random.laplace(0, 1.0/self.epsilon_dp)
            oa_payment = np.clip(oa_payment, 0, 1)

        # BTS
        bts_payment = 0.5
        if report_prob is not None and report_meta is not None:
            x = np.clip(report_prob, 0.01, 0.99)
            y = np.clip(report_meta, 0.01, 0.99)
            others = [nid for nid in self.nodes if nid != node_id 
                     and not self.nodes[nid]['banned']]
            if others:
                all_probs = []
                for oid in others:
                    all_probs.extend([p for tid, p, _ in self.prob_reports[oid] if tid != task_id])
                if all_probs:
                    f_others = np.median(all_probs)
                    info_score = np.log(x / y)
                    freq_score = np.log(f_others / y) if abs(f_others - y) > 0.01 else 0
                    bts_payment = 0.5 + 0.3 * info_score + 0.2 * freq_score
                    bts_payment += np.random.laplace(0, 1.0/self.epsilon_dp)
                    bts_payment = np.clip(bts_payment, 0, 1)

        # Verificación
        verified_payment = None
        if task_id in self.verified_tasks and task_id in self.ground_truth:
            truth = self.ground_truth[task_id]
            correct = (report_binary == truth)
            verified_payment = 1.0 if correct else 0.0
            self.verif_stats[node_id]['correct'] += int(correct)
            self.verif_stats[node_id]['total'] += 1
            self._check_slash(node_id)

        self.reports_history[node_id].append((task_id, report_binary, time.time()))
        if report_prob is not None:
            self.prob_reports[node_id].append((task_id, report_prob, report_meta))

        node['n_tasks'] += 1
        node['mean_payment'] = (node['mean_payment'] * n_tasks + oa_payment) / (n_tasks + 1)

        return {
            'oa_payment': oa_payment,
            'bts_payment': bts_payment,
            'verified_payment': verified_payment,
            'stake': node['stake'],
            'status': 'active' if not node['banned'] else 'banned'
        }

    def _check_slash(self, node_id):
        stats = self.verif_stats[node_id]
        n = stats['total']
        k = stats['correct']
        if n < 8:
            return
        p_value = binom.cdf(k, n, 0.5)
        accuracy = k / n
        node = self.nodes[node_id]
        if p_value < 0.01 and accuracy < 0.5:
            slash = node['stake'] * 0.5
            node['stake'] -= slash
            self.slash_log.append({'node': node_id, 'amount': slash, 
                                   'reason': 'worse_than_chance', 'p_value': p_value})
            if node['stake'] < 200:
                node['banned'] = True
                node['status'] = 'banned'
        elif accuracy < 0.55 and n >= 15:
            slash = node['stake'] * 0.2
            node['stake'] -= slash
            self.slash_log.append({'node': node_id, 'amount': slash,
                                   'reason': 'below_threshold', 'accuracy': accuracy})

    def get_node_score(self, node_id):
        stats = self.verif_stats[node_id]
        n = stats['total']
        if n == 0:
            return {
                'reliability': 0.5,
                'verified_accuracy': None,
                'n_verified': 0,
                'stake': self.nodes.get(node_id, {}).get('stake', 0.0),
                'banned': self.nodes.get(node_id, {}).get('banned', False)
            }
        acc = stats['correct'] / n
        p_worse = binom.cdf(stats['correct'], n, 0.5)
        return {
            'reliability': 1 - p_worse,
            'verified_accuracy': acc,
            'n_verified': n,
            'stake': self.nodes[node_id]['stake'],
            'banned': self.nodes[node_id]['banned']
        }

    def inject_honeypot(self, task_id, fake_event, expected_report):
        self.verified_tasks.add(task_id)
        self.ground_truth[task_id] = expected_report
        return task_id
