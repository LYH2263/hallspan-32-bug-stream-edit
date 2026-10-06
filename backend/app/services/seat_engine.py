"""Exam seating with an append-only seating journal.

排座按准考证号从小到大落座：考生以准考证号升序依次选座，每一次成功
落座都会向只追加（append-only）的流水账追加一行（准考证号、格子
row/col、次序 seq），seq 即实际落座先后（从 1 开始）。当前排座图必须
能由该段流水按 seq 从早到晚重放还原，对不上即视为失败（整场作废）。

硬约束（任一不满足就换格，换不到进未排）：
  * 与已落座者曼哈顿距离 >= min_dist；
  * 同试卷套不得四邻相邻；
  * 同一排上不得出现两个相同准考证尾号 —— 后到者只能另排他格或进未排，
    绝不允许为给后号腾格而改写先号已经提交的流水（流水只追加 ⇄ 回头挤位互斥）。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


class PlacementError(ValueError):
    """整场拒绝：准考证号为空或重复等致命数据问题。"""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("; ".join(problems))


@dataclass
class SeatAssign:
    candidate_id: int
    name: str
    ticket_no: str
    paper_id: int
    row: int
    col: int


@dataclass
class JournalEntry:
    """一条只追加流水：准考证号 + 格子 + 次序。"""
    seq: int
    ticket_no: str
    candidate_id: int
    row: int
    col: int


@dataclass
class Violation:
    kind: str
    a_id: int
    b_id: int
    detail: str


def manhattan(a: tuple[int, int], b: tuple[int, int]) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def neighbors4(r: int, c: int, rows: int, cols: int) -> list[tuple[int, int]]:
    out = []
    for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        nr, nc = r + dr, c + dc
        if 0 <= nr < rows and 0 <= nc < cols:
            out.append((nr, nc))
    return out


def ticket_tail(ticket_no: str) -> str:
    """准考证尾号：去掉空白后取最后一个字符。"""
    return str(ticket_no).strip()[-1:]


def validate_tickets(candidates: list[dict]) -> None:
    """号空或重复 → 整场拒绝（不排座、不写流水、不动图）。"""
    problems: list[str] = []
    seen: set[str] = set()
    for cand in candidates:
        ticket = str(cand.get("ticket_no") or "").strip()
        cid = cand.get("id")
        if not ticket:
            problems.append(f"考生 {cid} 准考证号为空")
            continue
        if ticket in seen:
            problems.append(f"准考证号重复：{ticket}")
        seen.add(ticket)
    if problems:
        raise PlacementError(problems)


def place_candidates(
    rows: int,
    cols: int,
    min_dist: int,
    candidates: list[dict],
) -> tuple[list[SeatAssign], list[dict], list[JournalEntry]]:
    """按准考证号从小到大依次落座；返回 (落座, 未排, 只追加流水)。

    落座顺序即准考证号升序（同号按 candidate_id 兜底），seq 从 1 开始，
    记录实际落座先后。落座过程中每个座位只增不改——先号已提交的格子与
    流水永不被后号挤动；后号不合法就换格，整场换不到合法格则进未排。
    """
    validate_tickets(candidates)

    order = sorted(candidates,
                   key=lambda c: (str(c["ticket_no"]).strip(), c.get("id", 0)))

    occupied: dict[tuple[int, int], SeatAssign] = {}
    unplaced: list[dict] = []
    journal: list[JournalEntry] = []
    seq = 0

    for cand in order:  # 按准考证号从小到大落座
        placed = False
        for r in range(rows):
            for c in range(cols):
                if (r, c) in occupied:
                    continue
                if not _seat_legal(r, c, rows, cols, min_dist, cand, occupied):
                    continue
                ticket = str(cand["ticket_no"]).strip()
                occupied[(r, c)] = SeatAssign(
                    cand["id"], cand["name"], ticket,
                    cand["paper_id"], r, c,
                )  # 只追加：一旦落定，后续考生不得改写此格
                seq += 1
                journal.append(JournalEntry(
                    seq=seq, ticket_no=ticket, candidate_id=cand["id"], row=r, col=c,
                ))
                placed = True
                break
            if placed:
                break
        if not placed:
            # 整场没有任何合法格子（含"同排已有相同尾号"）→ 进未排
            unplaced.append(cand)

    assigns = sorted(occupied.values(), key=lambda a: (a.row, a.col, a.candidate_id))
    if not replay_matches(rows, cols, assigns, journal):
        raise PlacementError(["排座流水无法重放当前排座图，本次排座作废"])
    return assigns, unplaced, journal


def _seat_legal(
    r: int,
    c: int,
    rows: int,
    cols: int,
    min_dist: int,
    cand: dict,
    occupied: dict[tuple[int, int], SeatAssign],
) -> bool:
    tail = ticket_tail(str(cand["ticket_no"]).strip())
    for pos, other in occupied.items():
        if manhattan((r, c), pos) < min_dist:
            return False
        if other.paper_id == cand["paper_id"] and (r, c) in neighbors4(pos[0], pos[1], rows, cols):
            return False
        # 同一排不得出现两个相同尾号：后到者另排，绝不挤动先到者。
        if other.row == r and ticket_tail(other.ticket_no) == tail:
            return False
    return True


def replay_journal(rows: int, cols: int, journal: list[JournalEntry]) -> dict[tuple[int, int], int]:
    """按流水次序 seq 从早到晚重放：逐格占位。格子被占用两次即流水非法。"""
    grid: dict[tuple[int, int], int] = {}
    prev_seq = 0
    for e in sorted(journal, key=lambda x: x.seq):
        if e.seq != prev_seq + 1:
            raise PlacementError([
                f"流水次序不连续：第 {prev_seq} 行之后出现 seq={e.seq}"
            ])
        prev_seq = e.seq
        pos = (e.row, e.col)
        if not (0 <= e.row < rows and 0 <= e.col < cols):
            raise PlacementError([f"流水第 {e.seq} 行格子越界：({e.row},{e.col})"])
        if pos in grid:
            raise PlacementError([f"流水第 {e.seq} 行与已提交流水争抢格子 {pos}（回头挤位）"])
        grid[pos] = e.candidate_id
    return grid


def replay_matches(rows: int, cols: int, assigns: list[SeatAssign],
                   journal: list[JournalEntry]) -> bool:
    """当前排座图必须能被该段流水按次序重放出来，对不上即失败。"""
    try:
        grid = replay_journal(rows, cols, journal)
    except PlacementError:
        return False
    expect = {(a.row, a.col): a.candidate_id for a in assigns}
    return grid == expect and len(grid) == len(assigns)


def find_violations(
    rows: int,
    cols: int,
    min_dist: int,
    assigns: list[SeatAssign],
) -> list[Violation]:
    viols: list[Violation] = []
    for i, a in enumerate(assigns):
        for b in assigns[i + 1:]:
            d = manhattan((a.row, a.col), (b.row, b.col))
            if d < min_dist:
                viols.append(Violation("distance", a.candidate_id, b.candidate_id,
                                       f"曼哈顿距离 {d} < 最小要求 {min_dist}"))
            if a.paper_id == b.paper_id and (b.row, b.col) in neighbors4(a.row, a.col, rows, cols):
                viols.append(Violation("same_paper_adjacent", a.candidate_id, b.candidate_id,
                                       f"同试卷套 {a.paper_id} 四邻相邻"))
            # 同排同尾号是独立违规类型，说明不得写成间距不足。
            if a.row == b.row and ticket_tail(a.ticket_no) == ticket_tail(b.ticket_no):
                viols.append(Violation("same_ticket_tail", a.candidate_id, b.candidate_id,
                                       f"同一排（第 {a.row + 1} 排）出现相同准考证尾号 "
                                       f"{ticket_tail(a.ticket_no)!r}：{a.ticket_no} 与 {b.ticket_no}"))
    return viols


def journal_to_dicts(journal: list[JournalEntry]) -> list[dict]:
    return [asdict(e) for e in journal]


def plan_to_dict(
    assigns: list[SeatAssign],
    unplaced: list[dict],
    viols: list[Violation],
    rows: int,
    cols: int,
    journal: list[JournalEntry] | None = None,
) -> dict:
    return {
        "rows": rows,
        "cols": cols,
        "assignments": [asdict(a) for a in assigns],
        "unplaced": unplaced,
        "violations": [asdict(v) for v in viols],
        "journal": journal_to_dicts(journal or []),
        "stats": {
            "seated": len(assigns),
            "unplaced": len(unplaced),
            "violations": len(viols),
            "capacity": rows * cols,
            "journal_entries": len(journal or []),
        },
    }
