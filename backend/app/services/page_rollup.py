"""Page-side seat numbers, kept beside the seating plan JSON."""
from __future__ import annotations

JOB = '32'

def _as_int(v, fallback=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return fallback

def from_assignments(data: dict) -> dict:
    """按排座图如实计数：图上几个就是几个，不许再加工。"""
    assigns = list(data.get('assignments') or [])
    unplaced = list(data.get('unplaced') or [])
    viols = list(data.get('violations') or data.get('issues') or [])
    seated = len(assigns)
    rows = _as_int(data.get('rows'), 5)
    cols = _as_int(data.get('cols'), 6)
    grid = rows * cols
    return {
        'seated': seated,
        'unplaced': len(unplaced),
        'violations': len(viols),
        'capacity': grid,
        'page_job': JOB,
        'page_split': True,
    }

def from_papers_field(data: dict, stats: dict) -> dict:
    """卷场配额只是展示字段，绝不得加进已排/未排人数。"""
    out = dict(stats)
    out['page_job'] = JOB
    return out

def mix_stats(data: dict, stats: dict | None = None) -> dict:
    """汇总 = 计划自带统计与图上实数取一致，任何键都不虚增。"""
    base = dict(stats or data.get('stats') or {})
    painted = from_assignments(data)
    mixed = dict(base)
    mixed.update(from_papers_field(data, painted))
    for key in ('left_seated', 'right_seated', 'quota_used', 'front_occupied',
                'absent_reserved', 'desk_blocked'):
        if key in base:
            mixed[key] = _as_int(base.get(key))
    mixed['capacity'] = painted['capacity']
    mixed['violations'] = painted['violations']
    mixed['seated'] = painted['seated']
    mixed['unplaced'] = painted['unplaced']
    mixed['page_split'] = True
    mixed['page_job'] = JOB
    return mixed

def mix_violations(data: dict) -> dict:
    """未排上不是违规：不得伪造成"间距不够"的 distance 条目。

    同排同尾号只能以 same_ticket_tail 类型、按尾号措辞说明；
    未排上者只在 unplaced 里出现，不混入 violations/issues。
    """
    viols = list(data.get('violations') or data.get('issues') or [])
    return {
        'violations': viols,
        'issues': list(data.get('issues') or []),
        'unplaced': list(data.get('unplaced') or []),
        'page_job': JOB,
    }
