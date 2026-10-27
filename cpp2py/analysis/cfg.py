from __future__ import annotations

from dataclasses import dataclass, field
from cpp2py.ir.model import IRFunction, Instruction, Opcode

@dataclass
class CFGEdge:
    source: BasicBlock
    target: BasicBlock
    kind: str = "normal"

@dataclass
class BasicBlock:
    block_id: int
    instructions: list[Instruction] = field(default_factory=list)
    predecessors: list[BasicBlock] = field(default_factory=list)
    successors: list[BasicBlock] = field(default_factory=list)
    outgoing_edges: list[CFGEdge] = field(default_factory=list)
    is_loop_head: bool = False

    def __hash__(self) -> int:
        return hash(self.block_id)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, BasicBlock):
            return False
        return self.block_id == other.block_id

    def __repr__(self) -> str:
        return f"Block({self.block_id}, instrs={len(self.instructions)}, loop_head={self.is_loop_head})"

class CFG:

    def __init__(self, func: IRFunction) -> None:
        self.func = func
        self.entry: BasicBlock | None = None
        self.blocks: list[BasicBlock] = []
        self._build()

    def _build(self) -> None:
        body = self.func.body
        if not body:
            return

        leaders: set[int] = {0}
        label_to_index: dict[str, int] = {}

        for idx, instr in enumerate(body):
            if instr.opcode == Opcode.LABEL:
                leaders.add(idx)
                label_name = instr.label_name or (str(instr.operands[0]) if instr.operands else "")
                label_to_index[label_name] = idx
            elif instr.opcode in (Opcode.JUMP, Opcode.BRANCH, Opcode.RETURN):
                if idx + 1 < len(body):
                    leaders.add(idx + 1)

        sorted_leaders = sorted(leaders)

        blocks: list[BasicBlock] = []
        index_to_block: dict[int, BasicBlock] = {}
        label_to_block: dict[str, BasicBlock] = {}

        for b_id, start_idx in enumerate(sorted_leaders):
            end_idx = sorted_leaders[b_id + 1] if b_id + 1 < len(sorted_leaders) else len(body)
            block_instrs = body[start_idx:end_idx]

            is_loop_head = False
            if block_instrs:
                first = block_instrs[0]
                if first.opcode == Opcode.LABEL:
                    label_name = first.label_name or (str(first.operands[0]) if first.operands else "")
                    label_to_block[label_name] = None
                    if first.role == "loop_head" or label_name.startswith("loop_head_"):
                        is_loop_head = True

            bb = BasicBlock(block_id=b_id, instructions=block_instrs, is_loop_head=is_loop_head)
            blocks.append(bb)
            index_to_block[start_idx] = bb
            if block_instrs and block_instrs[0].opcode == Opcode.LABEL:
                label_name = block_instrs[0].label_name or (str(block_instrs[0].operands[0]) if block_instrs[0].operands else "")
                label_to_block[label_name] = bb

        self.blocks = blocks
        self.entry = blocks[0]

        for b_id, bb in enumerate(blocks):
            if not bb.instructions:
                continue

            last = bb.instructions[-1]
            if last.opcode == Opcode.JUMP:
                target_label = last.label_name or (str(last.operands[0]) if last.operands else "")
                target_block = label_to_block.get(target_label)
                if target_block is not None:
                    self._add_edge(bb, target_block, kind="normal")

            elif last.opcode == Opcode.BRANCH:
                t_label = str(last.operands[1]) if len(last.operands) > 1 else ""
                f_label = str(last.operands[2]) if len(last.operands) > 2 else ""
                t_block = label_to_block.get(t_label)
                f_block = label_to_block.get(f_label)
                if t_block is not None:
                    self._add_edge(bb, t_block, kind="true")
                if f_block is not None:
                    self._add_edge(bb, f_block, kind="false")

            elif last.opcode == Opcode.RETURN:

                pass

            else:

                if b_id + 1 < len(blocks):
                    self._add_edge(bb, blocks[b_id + 1], kind="normal")

    def _add_edge(self, source: BasicBlock, target: BasicBlock, kind: str) -> None:
        edge = CFGEdge(source=source, target=target, kind=kind)
        source.successors.append(target)
        source.outgoing_edges.append(edge)
        target.predecessors.append(source)

    def reverse_post_order(self) -> list[BasicBlock]:
        if self.entry is None:
            return []

        visited: set[int] = set()
        post_order: list[BasicBlock] = []

        def dfs(bb: BasicBlock) -> None:
            visited.add(bb.block_id)
            for succ in bb.successors:
                if succ.block_id not in visited:
                    dfs(succ)
            post_order.append(bb)

        dfs(self.entry)
        post_order.reverse()
        return post_order
