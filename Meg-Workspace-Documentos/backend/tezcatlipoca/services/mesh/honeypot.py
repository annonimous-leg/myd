"""
Honeypot Engine: Inyección de tareas falsas con ground truth conocido.
"""

import numpy as np
from collections import defaultdict

class HoneypotEngine:
    def __init__(self, base_rate=0.03, adaptive_factor=2.0, 
                 covert_mode=True, detection_threshold=0.95):
        self.base_rate = base_rate
        self.adaptive_factor = adaptive_factor
        self.covert_mode = covert_mode
        self.detection_threshold = detection_threshold
        self.honeypots = {}
        self.detected_nodes = defaultdict(int)
        self.total_honeypots = 0

    def should_inject(self, task_id, node_variance=None, n_active_nodes=0):
        rate = self.base_rate
        if node_variance is not None and node_variance > 0.3:
            rate *= self.adaptive_factor
        if n_active_nodes > 20:
            rate *= 1.5
        return np.random.rand() < min(rate, 0.15)

    def generate_honeypot(self, task_id, task_type='binary', real_distribution=None):
        self.total_honeypots += 1
        if self.covert_mode and real_distribution is not None:
            truth = np.random.binomial(1, real_distribution)
        else:
            truth = np.random.binomial(1, 0.5)
        self.honeypots[task_id] = {
            'truth': truth,
            'injected_at': task_id,
            'type': task_type,
            'detected_by': set(),
            'failed_by': set()
        }
        return truth

    def evaluate_report(self, task_id, node_id, report):
        if task_id not in self.honeypots:
            return None
        hp = self.honeypots[task_id]
        correct = (report == hp['truth'])
        if correct:
            hp['detected_by'].add(node_id)
        else:
            hp['failed_by'].add(node_id)
            self.detected_nodes[node_id] += 1
        return {'correct': correct, 'truth': hp['truth'], 
                'failed_count': self.detected_nodes[node_id]}

    def get_node_suspicion(self, node_id, total_tasks_seen):
        failed = self.detected_nodes[node_id]
        total_hp = len([hp for hp in self.honeypots.values() 
                       if node_id in hp['failed_by'] or node_id in hp['detected_by']])
        if total_hp < 5:
            return {'suspicion': 0.0, 'confidence': 'low', 'n_honeypots': total_hp}
        from scipy.stats import binom
        p_value = 1 - binom.cdf(failed - 1, total_hp, 0.5)
        suspicion = failed / total_hp
        return {'suspicion': suspicion, 'p_value': p_value, 'failed': failed,
                'total_honeypots': total_hp, 'confidence': 'high' if total_hp > 20 else 'medium'}
