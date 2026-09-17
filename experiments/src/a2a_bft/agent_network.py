"""
A2A-BFT 多 Agent 通信层
实现 A2A 协议的消息传递
"""

import uuid
import json
import hashlib
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Callable
from enum import Enum
from collections import defaultdict


class MessageType(Enum):
    """A2A 消息类型"""
    TASK_SEND = "tasks.send"          # Client 分发 Task
    BFT_PROPOSE = "bft.propose"        # Worker 提交提案
    BFT_VALIDATE = "bft.validate"      # Worker 提交验证投票
    BFT_COMMIT = "bft.commit"          # Client 广播共识决策
    VIEW_CHANGE = "bft.view-change"    # 视图切换请求
    TASK_RESPONSE = "tasks.response"   # Worker 响应 Task


@dataclass
class A2AMessage:
    """A2A 协议消息"""
    message_id: str
    message_type: MessageType
    sender_did: str
    receiver_did: str
    payload: Dict
    timestamp: float
    signature: str = ""
    nonce: str = None

    def __post_init__(self):
        if self.nonce is None:
            self.nonce = uuid.uuid4().hex[:16]
        if not self.signature:
            self.signature = self._sign()

    def _sign(self) -> str:
        """计算消息签名"""
        content = f"{self.message_id}{self.sender_did}{self.receiver_did}{self.payload}{self.timestamp}{self.nonce}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]

    def verify(self) -> bool:
        """验证消息签名"""
        expected = self._sign()
        return self.signature == expected

    def to_dict(self) -> Dict:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender_did": self.sender_did,
            "receiver_did": self.receiver_did,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "signature": self.signature,
            "nonce": self.nonce
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'A2AMessage':
        return cls(
            message_id=data["message_id"],
            message_type=MessageType(data["message_type"]),
            sender_did=data["sender_did"],
            receiver_did=data["receiver_did"],
            payload=data["payload"],
            timestamp=data["timestamp"],
            signature=data.get("signature", ""),
            nonce=data.get("nonce")
        )


class AgentNode:
    """Agent 节点（具备 A2A 通信能力）"""

    def __init__(self, did: str, name: str = ""):
        self.did = did
        self.name = name or f"Agent_{did[:8]}"
        self.inbox: List[A2AMessage] = []
        self.outbox: List[A2AMessage] = []
        self.known_agents: Dict[str, str] = {}  # did -> address
        self.callbacks: Dict[MessageType, List[Callable]] = defaultdict(list)

    def register_callback(self, message_type: MessageType, callback: Callable):
        """注册消息处理回调"""
        self.callbacks[message_type].append(callback)

    def receive(self, message: A2AMessage) -> bool:
        """接收消息"""
        if not message.verify():
            print(f"[{self.name}] 消息验证失败!")
            return False

        self.inbox.append(message)

        # 触发回调
        for callback in self.callbacks[message.message_type]:
            try:
                callback(self, message)
            except Exception as e:
                print(f"[{self.name}] 回调执行失败: {e}")

        return True

    def send(self, target_did: str, message_type: MessageType, payload: Dict) -> Optional[A2AMessage]:
        """发送消息"""
        message = A2AMessage(
            message_id=uuid.uuid4().hex,
            message_type=message_type,
            sender_did=self.did,
            receiver_did=target_did,
            payload=payload,
            timestamp=time.time()
        )

        self.outbox.append(message)
        return message

    def process_inbox(self):
        """处理收件箱"""
        messages = self.inbox.copy()
        self.inbox.clear()

        for msg in messages:
            self.receive(msg)

    def get_messages(self) -> List[A2AMessage]:
        """获取所有待处理消息"""
        return self.inbox.copy()


class AgentNetwork:
    """Agent 网络（模拟 A2A 网络）"""

    def __init__(self):
        self.agents: Dict[str, AgentNode] = {}
        self.message_log: List[Dict] = []

    def register_agent(self, agent: AgentNode):
        """注册 Agent"""
        self.agents[agent.did] = agent
        print(f"[Network] 注册 Agent: {agent.name} ({agent.did[:16]}...)")

    def send_message(self, sender_did: str, message: A2AMessage) -> Optional[A2AMessage]:
        """发送消息"""
        if sender_did not in self.agents:
            print(f"[Network] 发送方不存在: {sender_did}")
            return None

        receiver_did = message.receiver_did
        if receiver_did not in self.agents:
            print(f"[Network] 接收方不存在: {receiver_did}")
            return None

        # 模拟网络延迟
        time.sleep(0.01)

        # 投递消息
        receiver = self.agents[receiver_did]
        receiver.receive(message)

        # 记录日志
        self.message_log.append({
            "timestamp": time.time(),
            "sender": sender_did[:16],
            "receiver": receiver_did[:16],
            "type": message.message_type.value,
            "success": True
        })

        return message

    def broadcast(self, sender_did: str, message_type: MessageType, payload: Dict, exclude: List[str] = None):
        """广播消息"""
        exclude = exclude or []
        for agent_did in self.agents:
            if agent_did != sender_did and agent_did not in exclude:
                message = A2AMessage(
                    message_id=uuid.uuid4().hex,
                    message_type=message_type,
                    sender_did=sender_did,
                    receiver_did=agent_did,
                    payload=payload,
                    timestamp=time.time()
                )
                self.send_message(sender_did, message)

    def get_stats(self) -> Dict:
        """获取网络统计"""
        return {
            "total_agents": len(self.agents),
            "total_messages": len(self.message_log),
            "messages_by_type": defaultdict(int)
        }


# 示例用法
if __name__ == "__main__":
    print("A2A-BFT 多 Agent 通信层测试")
    print("="*70)

    # 创建网络
    network = AgentNetwork()

    # 创建 Agent
    client = AgentNode("did:a2a:client", "Client")
    worker1 = AgentNode("did:a2a:worker1", "Worker1")
    worker2 = AgentNode("did:a2a:worker2", "Worker2")
    worker3 = AgentNode("did:a2a:worker3", "Worker3")

    # 注册到网络
    network.register_agent(client)
    network.register_agent(worker1)
    network.register_agent(worker2)
    network.register_agent(worker3)

    # 发送消息
    print("\n[测试] 发送 Task 消息")
    msg = client.send(
        target_did=worker1.did,
        message_type=MessageType.TASK_SEND,
        payload={"task_id": "task_001", "content": "计算 1+1"}
    )
    network.send_message(client.did, msg)

    # 广播
    print("[测试] 广播视图切换请求")
    network.broadcast(
        sender_did=worker2.did,
        message_type=MessageType.VIEW_CHANGE,
        payload={"new_view": 2}
    )

    # 统计
    print(f"\n网络统计: {network.get_stats()}")
    print("="*70)
