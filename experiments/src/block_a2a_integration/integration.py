"""
BlockA2A + A2A-BFT 集成层
实现 L1-L4 完整协议栈
"""

from typing import Dict, List, Optional
import json

# A2A-BFT 共识层
from a2a_bft.deepseek_worker import ConsensusLayer, DeepSeekWorker

# BlockA2A 组件（假设已存在）
class BlockA2AIntegration:
    """
    BlockA2A + A2A-BFT 集成层
    
    L1: 身份层 (DID)
    L2: 审计层 (Audit Trail)
    L3: 权限层 (Access Control)
    L4: 共识层 (BFT Consensus)
    """
    
    def __init__(self, n: int, f: int, s: int, api_key: str = None):
        self.n = n
        self.f = f
        self.s = s
        self.api_key = api_key
        
        # L4: 共识层
        self.consensus = ConsensusLayer(
            n=n, f=f, s=s,
            view_change_timeout=1,
            task_type='general'
        )
        
        # L1: 身份层 - Worker DID映射
        self.worker_dids = {}
        
        # L2: 审计层 - 共识历史
        self.audit_trail = []
        
        # L3: 权限层 - Worker权限
        self.worker_permissions = {}
    
    def register_worker(self, worker_id: int, did: str, permissions: List[str] = None):
        """L1: 注册Worker到身份层"""
        self.worker_dids[worker_id] = did
        self.worker_permissions[worker_id] = permissions or ['propose', 'vote', 'execute']
        print(f'[L1-Identity] Worker {worker_id} 注册: {did}')
    
    def audit_consensus(self, consensus_result: Dict):
        """L2: 审计共识结果"""
        proposal = consensus_result.get('proposal')
        proposal_hash = proposal.hash if hasattr(proposal, 'hash') else (proposal.get('hash') if isinstance(proposal, dict) else None)
        audit_entry = {
            'timestamp': consensus_result.get('timestamp'),
            'round': consensus_result.get('round'),
            'decision': consensus_result.get('decision'),
            'proposal_hash': proposal_hash,
            'votes': [
                {
                    'validator_id': v.validator_id if hasattr(v, 'validator_id') else v.get('validator_id'),
                    'verdict': v.verdict.value if hasattr(v, 'verdict') else v.get('verdict'),
                    'confidence': v.confidence if hasattr(v, 'confidence') else v.get('confidence')
                }
                for v in consensus_result.get('votes', [])
            ]
        }
        self.audit_trail.append(audit_entry)
        return audit_entry
    
    def check_permission(self, worker_id: int, action: str) -> bool:
        """L3: 检查Worker权限"""
        permissions = self.worker_permissions.get(worker_id, [])
        return action in permissions
    
    def run_consensus_with_integration(self, workers: List[DeepSeekWorker], question: str) -> Dict:
        """运行集成共识（L1-L4）"""
        print('='*80)
        print('BlockA2A + A2A-BFT 集成共识')
        print('='*80)
        
        # L1: 身份验证
        for worker in workers:
            if worker.worker_id not in self.worker_dids:
                print(f'[L1-ERROR] Worker {worker.worker_id} 未注册，跳过')
                continue
        
        # L4: 共识执行
        result = self.consensus.run_consensus(workers, question)
        
        # L2: 审计记录
        if result['decision'] in ['ACCEPT', 'REJECT']:
            self.audit_consensus(result)
        
        # L3: 权限检查（执行阶段）
        if result['decision'] == 'ACCEPT':
            proposal = result.get('proposal')
            proposer_id = proposal.proposer_id if hasattr(proposal, 'proposer_id') else proposal.get('proposer_id') if isinstance(proposal, dict) else None
            if proposer_id is not None and self.check_permission(proposer_id, 'execute'):
                print('[L3-Permission] 提案者有权执行')
            else:
                print('[L3-ERROR] 提案者无权执行，拒绝')
                result['decision'] = 'REJECT'
        
        return result
    
    def get_audit_report(self) -> Dict:
        """生成审计报告"""
        return {
            'total_consensus': len(self.audit_trail),
            'accept_count': sum(1 for a in self.audit_trail if a['decision'] == 'ACCEPT'),
            'reject_count': sum(1 for a in self.audit_trail if a['decision'] == 'REJECT'),
            'history': self.audit_trail[-10:]  # 最近10条
        }


def create_integrated_system(
    n: int, f: int, s: int,
    api_key: str = None
) -> BlockA2AIntegration:
    """创建集成系统"""
    system = BlockA2AIntegration(n=n, f=f, s=s, api_key=api_key)
    
    # 默认注册Worker
    for i in range(n):
        did = f'did:a2a-bft:worker_{i:04d}'
        system.register_worker(i, did)
    
    return system


# 使用示例
if __name__ == '__main__':
    print('BlockA2A + A2A-BFT 集成示例')
    print('='*80)
    
    # 创建集成系统
    system = create_integrated_system(n=5, f=1, s=1)
    
    # 创建Workers
    workers = []
    for i in range(5):
        if i == 0:
            w = DeepSeekWorker(worker_id=i, byzantine_type='strategic_reject', accuracy=0.3)
            w.is_byzantine = True
        elif i == 1:
            w = DeepSeekWorker(worker_id=i, accuracy=0.6)
            w.is_soft_fault = True
        else:
            w = DeepSeekWorker(worker_id=i, accuracy=0.9)
        workers.append(w)
    
    # 运行集成共识
    result = system.run_consensus_with_integration(workers, '计算 1234 * 5678 = ?')
    
    print(f'共识结果: {result["decision"]}')
    
    # 生成审计报告
    audit = system.get_audit_report()
    print(f'审计报告:')
    print(f'  总共识数: {audit["total_consensus"]}')
    print(f'  接受: {audit["accept_count"]}')
    print(f'  拒绝: {audit["reject_count"]}')
