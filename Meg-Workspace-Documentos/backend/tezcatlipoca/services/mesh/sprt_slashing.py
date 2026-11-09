"""
SPRT (Sequential Probability Ratio Test) para slashing en tiempo real.
Wald's SPRT: H0 (honesto, p=0.80) vs H1 (malicioso, p=0.20).
"""

import numpy as np
from typing import Dict, Optional

class SPRTSlashingFixed:
    def __init__(self, p0=0.80, p1=0.20, alpha=0.01, beta=0.05):
        self.p0 = p0
        self.p1 = p1
        self.alpha = alpha
        self.beta = beta
        self.A = (1 - beta) / alpha
        self.B = beta / (1 - alpha)
        self.sprt_state = {}

    def _llr(self, correct):
        if correct:
            return np.log(self.p0 / self.p1)
        else:
            return np.log((1 - self.p0) / (1 - self.p1))

    def update(self, node_id, correct):
        if node_id not in self.sprt_state:
            self.sprt_state[node_id] = {'log_lr': 0.0, 'n_samples': 0, 
                                        'decision': None, 'history': []}
        state = self.sprt_state[node_id]
        if state['decision'] is not None:
            return state['decision']

        llr = self._llr(correct)
        state['log_lr'] += llr
        state['n_samples'] += 1
        state['history'].append(correct)

        if state['log_lr'] >= np.log(self.A):
            state['decision'] = 'honest'
            state['evidence'] = {'log_lr': state['log_lr'], 'n': state['n_samples'],
                                 'p_est': sum(state['history'])/len(state['history'])}
            return 'honest'
        elif state['log_lr'] <= np.log(self.B):
            state['decision'] = 'slash'
            state['evidence'] = {'log_lr': state['log_lr'], 'n': state['n_samples'],
                                 'p_est': sum(state['history'])/len(state['history'])}
            return 'slash'
        return 'continue'

    def get_status(self, node_id):
        if node_id not in self.sprt_state:
            return {'decision': 'pending', 'n': 0, 'log_lr': 0}
        s = self.sprt_state[node_id]
        return {'decision': s['decision'] or 'continue', 'n': s['n_samples'],
                'log_lr': s['log_lr'], 'upper': np.log(self.A), 'lower': np.log(self.B),
                'p_est': sum(s['history'])/len(s['history']) if s['history'] else None}
