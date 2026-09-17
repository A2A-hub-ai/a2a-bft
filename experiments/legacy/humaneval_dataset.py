"""
HumanEval 数据集 - 用于 A2A-BFT 实验的编程任务
包含修复任务、算法实现、单元测试等
"""

# HumanEval 风格的任务数据集
HUMANEVAL_DATASET = [
    # === 修复类任务 (Fix) ===
    {
        "id": "humaneval_fix_001",
        "type": "fix",
        "description": "修复 add 函数中的 bug",
        "code": "def add(x, y):\n    return x - y",
        "expected": "return x + y",
        "test": "assert add(2, 3) == 5",
        "difficulty": "easy"
    },
    {
        "id": "humaneval_fix_002",
        "type": "fix",
        "description": "修复 factorial 边界条件",
        "code": "def factorial(n):\n    if n == 0:\n        return 1\n    return n * factorial(n-1)",
        "expected": "添加 n < 0 的处理",
        "test": "assert factorial(5) == 120\nassert factorial(0) == 1",
        "difficulty": "easy"
    },
    {
        "id": "humaneval_fix_003",
        "type": "fix",
        "description": "修复斐波那契数列",
        "code": "def fibonacci(n):\n    if n <= 0:\n        return 0\n    elif n == 1:\n        return 1\n    return fibonacci(n-1)",
        "expected": "添加 fibonacci(n-2)",
        "test": "assert fibonacci(10) == 55",
        "difficulty": "easy"
    },
    {
        "id": "humaneval_fix_004",
        "type": "fix",
        "description": "修复二分查找",
        "code": "def binary_search(arr, target):\n    left, right = 0, len(arr) - 1\n    while left <= right:\n        mid = (left + right) // 2\n        if arr[mid] == target:\n            return mid\n        elif arr[mid] < target:\n            left = mid\n        else:\n            right = mid - 1\n    return -1",
        "expected": "left = mid + 1",
        "test": "assert binary_search([1,2,3,4,5], 3) == 2",
        "difficulty": "medium"
    },
    {
        "id": "humaneval_fix_005",
        "type": "fix",
        "description": "修复冒泡排序",
        "code": "def bubble_sort(arr):\n    n = len(arr)\n    for i in range(n):\n        for j in range(0, n-i):\n            if arr[j] > arr[j+1]:\n                arr[j], arr[j+1] = arr[j+1], arr[j]\n    return arr",
        "expected": "range(0, n-i-1)",
        "test": "assert bubble_sort([3,1,2]) == [1,2,3]",
        "difficulty": "medium"
    },
    {
        "id": "humaneval_fix_006",
        "type": "fix",
        "description": "修复字符串反转",
        "code": "def reverse_string(s):\n    result = ''\n    for c in s:\n        result = c + result\n    return result",
        "expected": "已正确",
        "test": "assert reverse_string('hello') == 'olleh'",
        "difficulty": "easy"
    },
    {
        "id": "humaneval_fix_007",
        "type": "fix",
        "description": "修复最大公约数",
        "code": "def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a",
        "expected": "已正确",
        "test": "assert gcd(48, 18) == 6",
        "difficulty": "easy"
    },
    {
        "id": "humaneval_fix_008",
        "type": "fix",
        "description": "修复质数判断",
        "code": "def is_prime(n):\n    if n < 2:\n        return False\n    for i in range(2, n):\n        if n % i == 0:\n            return False\n    return True",
        "expected": "已正确，但效率可优化",
        "test": "assert is_prime(7) == True\nassert is_prime(4) == False",
        "difficulty": "medium"
    },
    # === 实现类任务 (Implement) ===
    {
        "id": "humaneval_impl_001",
        "type": "implement",
        "description": "实现快速排序",
        "code": "def quicksort(arr):\n    if len(arr) <= 1:\n        return arr\n    pivot = arr[len(arr) // 2]\n    left = [x for x in arr if x < pivot]\n    middle = [x for x in arr if x == pivot]\n    right = [x for x in arr if x > pivot]\n    return left + middle + right",
        "expected": "实现分区排序",
        "test": "assert quicksort([3,6,8,10,1,2,1]) == [1,1,2,3,6,8,10]",
        "difficulty": "medium"
    },
    {
        "id": "humaneval_impl_002",
        "type": "implement",
        "description": "实现链表反转",
        "code": "class ListNode:\n    def __init__(self, val=0, next=None):\n        self.val = val\n        self.next = next\n\ndef reverse_list(head):\n    prev = None\n    current = head\n    while current:\n        next_temp = current.next\n        current.next = prev\n        prev = current\n        current = next_temp\n    return prev",
        "expected": "实现链表反转",
        "test": "head = ListNode(1, ListNode(2, ListNode(3)))\nassert reverse_list(head).val == 3",
        "difficulty": "medium"
    },
    {
        "id": "humaneval_impl_003",
        "type": "implement",
        "description": "实现二叉树遍历",
        "code": "class TreeNode:\n    def __init__(self, val=0, left=None, right=None):\n        self.val = val\n        self.left = left\n        self.right = right\n\ndef inorder_traversal(root):\n    result = []\n    def dfs(node):\n        if node:\n            dfs(node.left)\n            result.append(node.val)\n            dfs(node.right)\n    dfs(root)\n    return result",
        "expected": "实现中序遍历",
        "test": "root = TreeNode(1, None, TreeNode(2, TreeNode(3)))\nassert inorder_traversal(root) == [1,3,2]",
        "difficulty": "medium"
    },
    {
        "id": "humaneval_impl_004",
        "type": "implement",
        "description": "实现LRU缓存",
        "code": "class LRUCache:\n    def __init__(self, capacity):\n        self.capacity = capacity\n        self.cache = {}\n\n    def get(self, key):\n        if key in self.cache:\n            return self.cache[key]\n        return -1\n\n    def put(self, key, value):\n        if key in self.cache:\n            self.cache[key] = value\n        else:\n            if len(self.cache) >= self.capacity:\n                self.cache.pop(next(iter(self.cache)))\n            self.cache[key] = value",
        "expected": "实现带有序列化的LRU",
        "test": "cache = LRUCache(2)\ncache.put(1, 1)\ncache.put(2, 2)\nassert cache.get(1) == 1",
        "difficulty": "hard"
    },
    {
        "id": "humaneval_impl_005",
        "type": "implement",
        "description": "实现两数之和",
        "code": "def two_sum(nums, target):\n    for i in range(len(nums)):\n        for j in range(i+1, len(nums)):\n            if nums[i] + nums[j] == target:\n                return [i, j]\n    return []",
        "expected": "优化为O(n)复杂度",
        "test": "assert two_sum([2,7,11,15], 9) == [0,1]",
        "difficulty": "easy"
    },
    {
        "id": "humaneval_impl_006",
        "type": "implement",
        "description": "实现栈操作",
        "code": "class Stack:\n    def __init__(self):\n        self.items = []\n\n    def push(self, item):\n        self.items.append(item)\n\n    def pop(self):\n        if not self.is_empty():\n            return self.items.pop()\n        return None\n\n    def is_empty(self):\n        return len(self.items) == 0",
        "expected": "实现标准栈操作",
        "test": "s = Stack()\ns.push(1)\ns.push(2)\nassert s.pop() == 2",
        "difficulty": "easy"
    },
    {
        "id": "humaneval_impl_007",
        "type": "implement",
        "description": "实现单调栈",
        "code": "def monotone_stack(arr):\n    result = []\n    stack = []\n    for num in arr:\n        while stack and stack[-1] >= num:\n            result.append(stack.pop())\n        stack.append(num)\n    while stack:\n        result.append(stack.pop())\n    return result",
        "expected": "实现单调递增栈",
        "test": "assert monotone_stack([3,1,2,4]) == [1,2,3,4]",
        "difficulty": "hard"
    },
    # === 算法验证类任务 (Verify) ===
    {
        "id": "humaneval_verify_001",
        "type": "verify",
        "description": "验证排序算法正确性",
        "code": "def selection_sort(arr):\n    for i in range(len(arr)):\n        min_idx = i\n        for j in range(i+1, len(arr)):\n            if arr[j] < arr[min_idx]:\n                min_idx = j\n        arr[i], arr[min_idx] = arr[min_idx], arr[i]\n    return arr",
        "expected": "验证算法正确性",
        "test": "assert selection_sort([5,3,8,1]) == [1,3,5,8]",
        "difficulty": "easy"
    },
    {
        "id": "humaneval_verify_002",
        "type": "verify",
        "description": "验证回文检测",
        "code": "def is_palindrome(s):\n    s = s.lower().replace(' ', '')\n    return s == s[::-1]",
        "expected": "验证边界条件",
        "test": "assert is_palindrome('A man a plan a canal Panama') == True",
        "difficulty": "easy"
    },
    {
        "id": "humaneval_verify_003",
        "type": "verify",
        "description": "验证矩阵转置",
        "code": "def transpose(matrix):\n    rows = len(matrix)\n    cols = len(matrix[0])\n    result = [[0]*rows for _ in range(cols)]\n    for i in range(rows):\n        for j in range(cols):\n            result[j][i] = matrix[i][j]\n    return result",
        "expected": "验证转置正确性",
        "test": "m = [[1,2],[3,4]]\nassert transpose(m) == [[1,3],[2,4]]",
        "difficulty": "medium"
    },
    {
        "id": "humaneval_verify_004",
        "type": "verify",
        "description": "验证拓扑排序",
        "code": "def topological_sort(n, edges):\n    from collections import defaultdict, deque\n    graph = defaultdict(list)\n    indegree = [0] * n\n    for u, v in edges:\n        graph[u].append(v)\n        indegree[v] += 1\n    queue = deque([i for i in range(n) if indegree[i] == 0])\n    result = []\n    while queue:\n        node = queue.popleft()\n        result.append(node)\n        for neighbor in graph[node]:\n            indegree[neighbor] -= 1\n            if indegree[neighbor] == 0:\n                queue.append(neighbor)\n    return result if len(result) == n else []",
        "expected": "验证有向无环图拓扑排序",
        "test": "assert len(topological_sort(4, [(0,1),(0,2),(1,3),(2,3)])) == 4",
        "difficulty": "hard"
    },
    {
        "id": "humaneval_verify_005",
        "type": "verify",
        "description": "验证最短路径",
        "code": "def dijkstra(n, edges, start):\n    import heapq\n    graph = [[] for _ in range(n)]\n    for u, v, w in edges:\n        graph[u].append((v, w))\n        graph[v].append((u, w))\n    dist = [float('inf')] * n\n    dist[start] = 0\n    heap = [(0, start)]\n    while heap:\n        d, u = heapq.heappop(heap)\n        if d > dist[u]:\n            continue\n        for v, w in graph[u]:\n            if dist[u] + w < dist[v]:\n                dist[v] = dist[u] + w\n                heapq.heappush(heap, (dist[v], v))\n    return dist",
        "expected": "验证Dijkstra算法",
        "test": "assert dijkstra(3, [(0,1,1),(1,2,2),(0,2,5)], 0) == [0,1,3]",
        "difficulty": "hard"
    }
]

# 按难度分类
HUMANEVAL_EASY = [t for t in HUMANEVAL_DATASET if t['difficulty'] == 'easy']
HUMANEVAL_MEDIUM = [t for t in HUMANEVAL_DATASET if t['difficulty'] == 'medium']
HUMANEVAL_HARD = [t for t in HUMANEVAL_DATASET if t['difficulty'] == 'hard']


def get_task(task_id=None, task_type=None, difficulty=None):
    """获取指定任务"""
    tasks = HUMANEVAL_DATASET
    if task_id:
        for t in tasks:
            if t['id'] == task_id:
                return t
    if task_type:
        tasks = [t for t in tasks if t['type'] == task_type]
    if difficulty:
        tasks = [t for t in tasks if t['difficulty'] == difficulty]
    if tasks:
        return tasks[0]
    return None


def get_random_tasks(n, exclude_ids=None):
    """获取 n 个随机任务"""
    import random
    exclude = exclude_ids or []
    available = [t for t in HUMANEVAL_DATASET if t['id'] not in exclude]
    return random.sample(available, min(n, len(available)))


def format_task_for_llm(task):
    """将任务格式化为 LLM 提示"""
    if task['type'] == 'fix':
        return f"""修复以下 Python 代码中的 bug：

```python
{task['code']}
```

预期正确行为：{task['expected']}

测试用例：
```python
{task['test']}
```

请输出修复后的完整代码。"""
    elif task['type'] == 'implement':
        return f"""实现以下 Python 函数：

```python
{task['code']}
```

功能要求：{task['description']}

测试用例：
```python
{task['test']}
```

请输出完整的实现代码。"""
    else:
        return f"""验证以下 Python 代码的正确性：

```python
{task['code']}
```

验证目标：{task['description']}

测试用例：
```python
{task['test']}
```

请分析并验证代码是否符合预期。"""


if __name__ == "__main__":
    # 测试数据集
    print("HumanEval 数据集统计:")
    print(f"  总数: {len(HUMANEVAL_DATASET)}")
    print(f"  Easy: {len(HUMANEVAL_EASY)}")
    print(f"  Medium: {len(HUMANEVAL_MEDIUM)}")
    print(f"  Hard: {len(HUMANEVAL_HARD)}")
    print()
    print("示例任务:")
    task = HUMANEVAL_DATASET[0]
    print(f"  ID: {task['id']}")
    print(f"  类型: {task['type']}")
    print(f"  描述: {task['description']}")
    print(f"  难度: {task['difficulty']}")
