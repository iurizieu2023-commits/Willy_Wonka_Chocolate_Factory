# core/item.py
import threading
import time
import random
from typing import Optional
from utils.colors import Color
from core.chocolate_type import ChocolateType


class Item:
    _id_counter = 0
    _id_lock = threading.Lock()

    def __init__(self) -> None:
        # stable id generation for multi-thread factories
        with Item._id_lock:
            self.id = f"item-{Item._id_counter}"
        Item._id_counter += 1

        self.created_at = time.time()
        
        # Golden ticket (rare - 10% chance)
        self.is_golden = random.random() < 0.04
        # "bar" / "coin" / "bunny" / etc.
        
        # Phase 1: Multi-flavour chocolate bars (DEPRECATED in favor of bar_type)
        self.flavor = random.choice(["hazelnut", "chocolate", "caramel"])
        
        # Phase 11: Chocolate bar type (set by FillingStation)
        self.bar_type: Optional[ChocolateType] = None
        
        self.filling = None        # "caramel" / "hazelnut" / ...
        self.wrapper = None        # "gold" / "purple" / ...

        # --- lifecycle/timing (throughput & latency metrics) ---
        self.created_at = time.time()
        self.current_stage = "created"
        self.stage_times = {
            "created": (self.created_at, self.created_at),
            "crushing": (None, None),
            "molding": (None, None),
            "filling": (None, None),
            "wrapping": (None, None),
            "qc": (None, None),
            "boxing": (None, None),
            "shipped": (None, None),
        }
        self.history = []


        self.qc_passed = None      # None/True/False
        self.defective = False
        self.defect_reason = None
        # Phase 1: Initialize quality_score to 1.0 (perfect quality at creation)
        self.quality_score = 1.0
        self.rework_count = 0

        # economics
        self.cost = 0.0
        self.value_added = 0.0
        self.theft_loss = 0.0

        # logistics hints
        self.destination_city = None
        self.priority = 0

    # Presentation (keeps former emoji behavior; colors optional)
    def icon(self) -> str:
        if self.is_golden:
            return f"{Color.YELLOW}🌟{Color.RESET}" if hasattr(Color, "YELLOW") else "🌟"
        return "🍫"

    def __repr__(self) -> str:
        if self.is_golden:
            return f"{Color.YELLOW}GoldenItem({self.id}){Color.RESET}" if hasattr(Color, "YELLOW") else f"GoldenItem({self.id})"
        return f"Item({self.id})"


    # Lifecycle — called by stations’ template-method hooks

    def stage_start(self, name: str) -> None:
        self.current_stage = name
        start, end = self.stage_times.get(name, (None, None))
        if start is None:
            self.stage_times[name] = (time.time(), None)
        self._log("stage_start", {"stage": name})

    def stage_end(self, name: str) -> None:
        start, end = self.stage_times.get(name, (None, None))
        self.stage_times[name] = (start, time.time())
        self._log("stage_end", {"stage": name})

    def latency_total(self) -> float:
        return max(0.0, time.time() - self.created_at)


    # Quality & rework — Strategy-ready helpers for QC

    def mark_defect(self, reason: str, score: float = None) -> None:
        self.defective = True
        self.defect_reason = reason
        if score is not None:
            self.quality_score = score
        self.qc_passed = False
        self._log("defect", {"reason": reason, "score": self.quality_score})

    def clear_defect(self) -> None:
        self.defective = False
        self.defect_reason = None
        self.qc_passed = None
        self.rework_count += 1
        self._log("reworked", {"count": self.rework_count})

    def pass_qc(self, score: float = None) -> None:
        self.qc_passed = True
        if score is not None:
            self.quality_score = score
        self._log("qc_pass", {"score": self.quality_score})


    # Economics — used by stations/supervisor/events

    def add_cost(self, amount: float, reason: str) -> None:
        if amount > 0:
            self.cost += amount
            self._log("cost_add", {"amount": amount, "reason": reason})

    def add_value(self, amount: float, reason: str) -> None:
        if amount > 0:
            self.value_added += amount
            self._log("value_add", {"amount": amount, "reason": reason})

    def record_theft(self, amount: float, event: str) -> None:
        if amount > 0:
            self.theft_loss += amount
            self._log("theft_loss", {"amount": amount, "event": event})

    def profit_estimate(self) -> float:
        return self.value_added - self.cost - self.theft_loss


    # Logistics hints

    def set_destination(self, city: str, priority: int = None) -> None:
        self.destination_city = city
        if priority is not None:
            self.priority = int(priority)
        self._log("destination_set", {"city": city, "priority": self.priority})


    # Observer-friendly snapshot for dashboard/supervisor

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "icon": "🌟" if self.is_golden else "🍫",
            "golden": self.is_golden,
            "created_at": self.created_at,
            "stage": self.current_stage,
            "stage_times": self.stage_times,
            "latency_total": self.latency_total(),
            "shape": self.shape,
            "bar_type": self.bar_type.value if self.bar_type else None,
            "filling": self.filling,
            "wrapper": self.wrapper,
            "temperature": self.temperature,
            "qc_passed": self.qc_passed,
            "defective": self.defective,
            "defect_reason": self.defect_reason,
            "quality_score": self.quality_score,
            "rework_count": self.rework_count,
            "cost": self.cost,
            "value_added": self.value_added,
            "theft_loss": self.theft_loss,
            "profit_estimate": self.profit_estimate(),
            "destination_city": self.destination_city,
            "priority": self.priority,
        }


    # internal

    def _log(self, event: str, details: dict) -> None:
        self.history.append((time.time(), event, dict(details)))
