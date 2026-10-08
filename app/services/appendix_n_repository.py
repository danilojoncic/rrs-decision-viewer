from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode


@dataclass(frozen=True)
class AppendixRule:
    number: str
    title: str
    text: str
    section: str

    @property
    def label(self) -> str:
        if self.title:
            return f"{self.number} {self.title}"
        return self.number


@dataclass(frozen=True)
class AppendixNScenario:
    body: str = "full_jury"
    matter: str = "part5"
    event_group: str = "standard"
    members: int = 5
    international_judges: int = 3
    national_authorities: int = 5
    max_same_authority: int = 1
    independent: bool = True
    appointed: bool = True
    na_approval_required: bool = False
    na_notice_posted: bool = True
    illness_emergency: bool = False
    no_replacements: bool = False
    ws_authorized: bool = False
    ws_letter_posted: bool = False
    oa_directs_otherwise: bool = False
    party_dissatisfied: bool = False
    facts_only: bool = False
    review_requested_in_time: bool = False
    review_panel_compliant: bool = False
    panel_failed_to_agree: bool = False
    chair_referred_deadlock: bool = False
    conflict_mode: str = "none"
    presenter_in_panel: bool = False
    presenter_in_jury: bool = False
    materials_disclosed: bool = True
    panel_investigated_before_hearing: bool = False
    ethics_procedure_applies: bool = False

    @property
    def body_label(self) -> str:
        return {
            "full_jury": "Full jury",
            "panel": "Panel",
            "emergency": "Illness or emergency panel",
            "recusal": "Conflict or recusal panel",
            "world_sailing_three": "World Sailing three-member jury",
        }.get(self.body, "Full jury")

    @property
    def matter_label(self) -> str:
        return {
            "part5": "Protest, redress or Part 5 matter",
            "eligibility": "Eligibility, measurement or rating certificate",
            "substitution": "Substitution of competitor, boat or equipment",
            "referred": "Matter referred by OA, RC or technical committee",
            "advisory": "Advice requested by OA, RC or technical committee",
            "misconduct": "Misconduct hearing under rule 69",
        }.get(self.matter, "Protest, redress or Part 5 matter")

    @property
    def group_label(self) -> str:
        if self.event_group == "mnq":
            return "Groups M, N or Q"
        return "Standard event group"


@dataclass(frozen=True)
class SimulatorFinding:
    severity: str
    title: str
    detail: str
    rules: tuple[str, ...]


@dataclass(frozen=True)
class SimulatorResult:
    verdict: str
    tone: str
    hearing_scope: str
    constitution_label: str
    findings: list[SimulatorFinding]
    next_actions: list[str]
    active_rule_numbers: list[str]


class AppendixNRepository:
    def __init__(self, rules_path: Path) -> None:
        self.rules_path = rules_path
        self._signature: tuple[int, int] | None = None
        self._rules: list[AppendixRule] = []
        self._rules_by_number: dict[str, AppendixRule] = {}

    def rules(self) -> list[AppendixRule]:
        self._refresh_if_changed()
        return self._rules

    def rule(self, number: str) -> AppendixRule | None:
        self._refresh_if_changed()
        return self._rules_by_number.get(number)

    def evaluate(self, scenario: AppendixNScenario) -> SimulatorResult:
        findings: list[SimulatorFinding] = []
        active_rules: set[str] = set()

        def add(severity: str, title: str, detail: str, *rules: str) -> None:
            findings.append(SimulatorFinding(severity, title, detail, tuple(rules)))
            active_rules.update(rules)

        group_max_same = 3 if scenario.event_group == "mnq" else 2
        group_min_authorities = 2 if scenario.event_group == "mnq" else 3
        majority_ij = scenario.international_judges > scenario.members / 2

        self._evaluate_hearing_scope(scenario, add)

        if scenario.body == "world_sailing_three":
            self._evaluate_world_sailing_three(
                scenario,
                add,
                group_min_authorities,
                group_max_same,
            )
        else:
            if scenario.independent:
                add("pass", "Independent from RC and technical committee", "The selected body has no race committee or technical committee members.", "N1.1")
            else:
                add("fail", "Independence problem", "An international jury must be independent of, and have no members from, the race committee or technical committee.", "N1.1")

            if scenario.appointed:
                add("pass", "Appointment route present", "The selected body has an appointment route through the organizing authority or World Sailing.", "N1.1")
            else:
                add("fail", "Appointment route missing", "Appendix N requires the international jury to be appointed through the rule N1.1 pathway.", "N1.1")

            if scenario.body == "full_jury":
                self._evaluate_full_jury(scenario, add, majority_ij, group_max_same)
            elif scenario.body == "panel":
                self._evaluate_panel(scenario, add, majority_ij, group_min_authorities)
            elif scenario.body == "emergency":
                self._evaluate_emergency(scenario, add, group_min_authorities)
            elif scenario.body == "recusal":
                self._evaluate_recusal(scenario, add)

            if scenario.na_approval_required:
                if scenario.na_notice_posted:
                    add("pass", "National authority notice posted", "Required national authority approval is included in the sailing instructions or official notice board.", "N1.8")
                else:
                    add("fail", "National authority notice missing", "When national authority approval is required, notice of that approval must appear in the sailing instructions or on the official notice board.", "N1.8")

        self._evaluate_conflict(scenario, add)
        self._evaluate_panel_procedure(scenario, add)
        if scenario.matter == "misconduct":
            self._evaluate_misconduct(scenario, add)

        failures = [finding for finding in findings if finding.severity == "fail"]
        warnings = [finding for finding in findings if finding.severity == "warn"]
        if failures:
            verdict = "Not ready"
            tone = "danger"
            constitution_failure = any(
                rule
                in {"N1.1", "N1.2", "N1.3", "N1.4", "N1.5", "N1.6", "N1.7", "N1.8"}
                for finding in failures
                for rule in finding.rules
            )
            if constitution_failure:
                constitution_label = "The selected body is not properly constituted. Decisions may be appealable if it acts in this state."
                active_rules.add("N1.9")
            else:
                constitution_label = "The selected combination has blocking Appendix N procedure issues that should be fixed before the hearing proceeds."
            next_actions = [finding.title for finding in failures[:4]]
        elif warnings:
            verdict = "Needs attention"
            tone = "warn"
            constitution_label = "The selected pathway can work, but the warning items should be resolved before the hearing proceeds."
            next_actions = [finding.title for finding in warnings[:4]]
        else:
            verdict = "Ready"
            tone = "pass"
            constitution_label = "The selected Appendix N pathway is properly constituted for the simulated hearing."
            next_actions = ["Proceed with the selected hearing pathway."]

        return SimulatorResult(
            verdict=verdict,
            tone=tone,
            hearing_scope=scenario.matter_label,
            constitution_label=constitution_label,
            findings=findings,
            next_actions=next_actions,
            active_rule_numbers=sorted(active_rules, key=_rule_sort_key),
        )

    def presets(self) -> list[dict[str, str]]:
        return [
            {
                "title": "Standard jury",
                "description": "Five members, majority IJ, standard authority spread.",
                "query": _preset_query(body="full_jury", members=5, international_judges=3, national_authorities=5, max_same_authority=1),
            },
            {
                "title": "Groups M/N/Q panel",
                "description": "Three-member panel with the reduced authority spread.",
                "query": _preset_query(body="panel", event_group="mnq", members=3, international_judges=2, national_authorities=2, max_same_authority=2),
            },
            {
                "title": "Emergency panel",
                "description": "Four remain, two IJs, no qualified replacements.",
                "query": _preset_query(body="emergency", members=4, international_judges=2, national_authorities=3, max_same_authority=2, illness_emergency=True, no_replacements=True),
            },
            {
                "title": "Conflict recusal",
                "description": "Three remain after a doubtful conflict issue.",
                "query": _preset_query(body="recusal", members=3, international_judges=2, national_authorities=3, max_same_authority=1, no_replacements=True, conflict_mode="doubt"),
            },
            {
                "title": "WS three-member",
                "description": "Limited authorization with all members as IJs.",
                "query": _preset_query(body="world_sailing_three", members=3, international_judges=3, national_authorities=3, max_same_authority=1, ws_authorized=True, ws_letter_posted=True),
            },
            {
                "title": "Panel review request",
                "description": "Dissatisfied party asks in time for a compliant panel.",
                "query": _preset_query(body="panel", members=3, international_judges=2, national_authorities=3, max_same_authority=1, party_dissatisfied=True, review_requested_in_time=True, review_panel_compliant=True),
            },
            {
                "title": "Deadlocked panel",
                "description": "Panel fails to agree and the chair refers the matter.",
                "query": _preset_query(body="panel", members=3, international_judges=2, national_authorities=3, max_same_authority=1, panel_failed_to_agree=True, chair_referred_deadlock=True),
            },
            {
                "title": "Rule 69 hearing",
                "description": "Presenter separate from panel, material disclosed.",
                "query": _preset_query(body="panel", matter="misconduct", members=3, international_judges=2, national_authorities=3, max_same_authority=1, materials_disclosed=True),
            },
        ]

    def _evaluate_hearing_scope(self, scenario: AppendixNScenario, add: Any) -> None:
        if scenario.matter == "part5":
            add("pass", "Part 5 matter belongs with the jury", "The international jury is responsible for protests, redress requests and other Part 5 matters.", "N2.1")
        elif scenario.matter in {"eligibility", "substitution"}:
            if scenario.oa_directs_otherwise:
                add("warn", "Organizing authority directed otherwise", "For this matter Appendix N assigns the decision to the jury unless the organizing authority directs otherwise.", "N2.2")
            else:
                add("pass", "Assigned decision matter", "Appendix N assigns this eligibility, measurement, rating or substitution decision to the jury unless the organizing authority directs otherwise.", "N2.2")
        elif scenario.matter == "referred":
            add("pass", "Referred matter", "The jury decides matters referred by the organizing authority, race committee or technical committee.", "N2.3")
        elif scenario.matter == "advisory":
            add("pass", "Advisory request", "When asked by the organizing authority, race committee or technical committee, the jury advises on matters affecting fairness.", "N2.1")
        elif scenario.matter == "misconduct":
            add("pass", "Rule 69 misconduct pathway", "Appendix N includes extra misconduct procedure checks for hearings under rule 69.", "N4")

    def _evaluate_full_jury(self, scenario: AppendixNScenario, add: Any, majority_ij: bool, group_max_same: int) -> None:
        if scenario.members >= 5:
            add("pass", "At least five members", "A full international jury has at least five members.", "N1.2")
        else:
            add("fail", "Too few members for a full jury", "A full international jury needs at least five members unless an Appendix N exception applies.", "N1.2", "N1.5", "N1.6", "N1.7")

        if majority_ij:
            add("pass", "International Judge majority", "A majority of the selected members are International Judges.", "N1.2")
        else:
            add("fail", "No IJ majority", "A majority of the full jury must be International Judges.", "N1.2")

        if scenario.max_same_authority <= group_max_same:
            add("pass", "National authority spread", f"No national authority has more than {group_max_same} member(s) in this event group.", "N1.3")
        else:
            add("fail", "Too many from one national authority", f"This event group allows no more than {group_max_same} member(s) from the same national authority.", "N1.3")

    def _evaluate_panel(self, scenario: AppendixNScenario, add: Any, majority_ij: bool, group_min_authorities: int) -> None:
        if scenario.members >= 3:
            add("pass", "Panel has at least three members", "A panel may hear with at least three members.", "N1.4")
        else:
            add("fail", "Panel too small", "A panel needs at least three members.", "N1.4")

        if majority_ij:
            add("pass", "Panel IJ majority", "A majority of the selected panel are International Judges.", "N1.4")
        else:
            add("fail", "Panel lacks IJ majority", "A panel needs a majority of International Judges.", "N1.4")

        if scenario.national_authorities >= group_min_authorities:
            add("pass", "Panel authority spread", f"The panel includes at least {group_min_authorities} national authorities for this event group.", "N1.4")
        else:
            add("fail", "Panel authority spread too narrow", f"The panel needs members from at least {group_min_authorities} national authorities in this event group.", "N1.4")

    def _evaluate_emergency(self, scenario: AppendixNScenario, add: Any, group_min_authorities: int) -> None:
        if scenario.illness_emergency and scenario.no_replacements:
            add("pass", "Emergency condition present", "The fewer-than-five pathway is tied to illness or emergency with no qualified replacements available.", "N1.5")
        else:
            add("fail", "Emergency exception incomplete", "Rule N1.5 needs illness or emergency and no qualified replacements available.", "N1.5")

        if 3 <= scenario.members < 5:
            add("pass", "Emergency member count", "The remaining body has three or four members.", "N1.5")
        else:
            add("fail", "Emergency count outside N1.5", "Rule N1.5 applies when fewer than five remain, but at least three members are still present.", "N1.5")

        if scenario.international_judges >= 2:
            add("pass", "At least two IJs remain", "The emergency body has at least two International Judges.", "N1.5")
        else:
            add("fail", "Not enough IJs remain", "The emergency body needs at least two International Judges.", "N1.5")

        if scenario.national_authorities >= group_min_authorities:
            add("pass", "Emergency authority spread", f"The remaining body includes at least {group_min_authorities} national authorities for this event group.", "N1.5")
        else:
            add("fail", "Emergency authority spread too narrow", f"With three or four members, the body needs at least {group_min_authorities} national authorities for this event group.", "N1.5")

    def _evaluate_recusal(self, scenario: AppendixNScenario, add: Any) -> None:
        if scenario.no_replacements:
            add("pass", "No qualified replacements", "The recusal pathway is available when replacement members are not available.", "N1.6")
        else:
            add("warn", "Replacement availability unresolved", "Rule N1.6 is the fallback when some members should not participate and no qualified replacements are available.", "N1.6")

        if scenario.members >= 3:
            add("pass", "At least three remain", "At least three members remain to discuss and decide.", "N1.6")
        else:
            add("fail", "Too few remain after recusal", "At least three members must remain under rule N1.6.", "N1.6")

        if scenario.international_judges >= 2:
            add("pass", "At least two remaining IJs", "At least two International Judges remain.", "N1.6")
        else:
            add("fail", "Not enough IJs remain after recusal", "At least two International Judges must remain under rule N1.6.", "N1.6")

    def _evaluate_world_sailing_three(self, scenario: AppendixNScenario, add: Any, group_min_authorities: int, group_max_same: int) -> None:
        if scenario.ws_authorized:
            add("pass", "World Sailing authorization present", "The limited three-member exception has World Sailing authorization.", "N1.7")
        else:
            add("fail", "World Sailing authorization missing", "A three-member international jury needs World Sailing authorization under rule N1.7.", "N1.7")

        if scenario.members == 3:
            add("pass", "Exactly three members", "The limited exception is for a total of only three members.", "N1.7")
        else:
            add("fail", "Wrong member count for N1.7", "Rule N1.7 authorizes a total of only three members.", "N1.7")

        if scenario.international_judges == scenario.members == 3:
            add("pass", "All members are IJs", "Every member is an International Judge.", "N1.7")
        else:
            add("fail", "All three must be IJs", "Under rule N1.7 all three members must be International Judges.", "N1.7")

        if scenario.national_authorities >= group_min_authorities and scenario.max_same_authority <= group_max_same:
            add("pass", "N1.7 authority spread", f"The three-member jury satisfies the authority spread for {scenario.group_label}.", "N1.7")
        else:
            add("fail", "N1.7 authority spread problem", f"The members must come from at least {group_min_authorities} national authorities for {scenario.group_label}.", "N1.7")

        if scenario.ws_letter_posted:
            add("pass", "Authorization published", "The authorization is stated in the approval letter, notice of race or sailing instructions, and posted.", "N1.7")
        else:
            add("fail", "Authorization publication missing", "The N1.7 authorization must be stated in the approval documents and posted on the official notice board.", "N1.7")

    def _evaluate_conflict(self, scenario: AppendixNScenario, add: Any) -> None:
        if scenario.conflict_mode == "none":
            return
        if scenario.conflict_mode == "nationality":
            add("pass", "Nationality or club alone is not significant", "Appendix N says nationality, club membership or similar does not by itself create a significant conflict.", "N3.1")
        elif scenario.conflict_mode == "doubt":
            add("warn", "Conflict doubt points to N1.6", "In case of doubt, the hearing should proceed as permitted by rule N1.6.", "N3.1", "N1.6")
        elif scenario.conflict_mode == "significant":
            if scenario.body == "recusal":
                add("pass", "Significant conflict handled by recusal pathway", "The selected recusal pathway keeps the body constituted while conflicted members do not participate.", "N3.1", "N1.6")
            else:
                add("fail", "Significant conflict not handled", "A significant conflict should be handled with considerable weight on fairness because international jury decisions cannot be appealed.", "N3.1")

    def _evaluate_panel_procedure(self, scenario: AppendixNScenario, add: Any) -> None:
        if scenario.party_dissatisfied:
            if scenario.facts_only:
                add("warn", "Facts-found exception", "The entitlement to a further panel hearing does not apply concerning the facts found.", "N1.4")
            elif not scenario.review_requested_in_time:
                add("warn", "Review request out of time", "A dissatisfied party must request the further hearing within 30 minutes or the sailing-instruction time limit.", "N1.4")
            elif scenario.review_panel_compliant:
                add("pass", "Compliant review panel available", "The dissatisfied party can be heard by a panel composed in compliance with N1.1, N1.2 and N1.3.", "N1.4", "N1.1", "N1.2", "N1.3")
            else:
                add("fail", "Compliant review panel missing", "A timely dissatisfied party is entitled to a hearing by a panel composed in compliance with N1.1, N1.2 and N1.3, except concerning facts found.", "N1.4")

        if scenario.panel_failed_to_agree:
            if scenario.chair_referred_deadlock:
                add("pass", "Deadlock referred", "When a panel fails to agree, the chair refers the matter to a properly constituted panel with as many members as possible.", "N3.2")
            else:
                add("fail", "Deadlock not referred", "If a panel fails to agree, the chair should refer the matter to a properly constituted panel, possibly the full jury.", "N3.2")

    def _evaluate_misconduct(self, scenario: AppendixNScenario, add: Any) -> None:
        if scenario.ethics_procedure_applies:
            add("warn", "Code of Ethics may override", "Specific Code of Ethics procedures override conflicting provisions of Appendix N.", "N4.1")

        if scenario.presenter_in_panel:
            add("fail", "Presenter cannot sit on hearing panel", "The person presenting rule 69 allegations must not be a member of the hearing panel.", "N4.2")
        elif scenario.presenter_in_jury:
            add("pass", "Presenter may be jury member", "The presenter is not on the hearing panel and may be a member of the jury.", "N4.2")
        else:
            add("pass", "Presenter separate from panel", "The presenter is separate from the hearing panel.", "N4.2")

        if scenario.materials_disclosed:
            add("pass", "Investigation material disclosed", "Material gathered in the investigation is disclosed before the hearing begins.", "N4.2", "N4.4")
        else:
            add("fail", "Disclosure missing", "The person subject to the rule 69 allegation must receive the material gathered and disclosed to the panel before the hearing begins.", "N4.2", "N4.4")

        if scenario.panel_investigated_before_hearing:
            add("fail", "Panel investigated before hearing", "Before the hearing, the panel should not act as investigator to the extent practically possible.", "N4.3")
        else:
            add("pass", "Panel not acting as investigator", "The hearing panel has not acted as the investigator before the hearing.", "N4.3")

    def _refresh_if_changed(self) -> None:
        signature = self._current_signature()
        if signature == self._signature:
            return

        if not self.rules_path.exists():
            self._rules = []
            self._rules_by_number = {}
            self._signature = signature
            return

        payload = json.loads(self.rules_path.read_text(encoding="utf-8-sig"))
        section = ""
        rules: list[AppendixRule] = []
        for item in payload:
            if item.get("appendix") != "N":
                continue
            number = str(item.get("number") or "")
            title = str(item.get("title") or "")
            text = str(item.get("text") or "")
            if title:
                section = f"{number} {title}"
            rules.append(AppendixRule(number=number, title=title, text=text, section=section))

        self._rules = rules
        self._rules_by_number = {rule.number: rule for rule in rules}
        self._signature = signature

    def _current_signature(self) -> tuple[int, int]:
        if not self.rules_path.exists():
            return (0, 0)
        stat = self.rules_path.stat()
        return (stat.st_size, stat.st_mtime_ns)


def _preset_query(**overrides: object) -> str:
    values = AppendixNScenario().__dict__ | overrides
    return urlencode({key: _query_value(value) for key, value in values.items()})


def _query_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _rule_sort_key(number: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in number.replace("N", "").split("."):
        if piece.isdigit():
            parts.append(int(piece))
    return tuple(parts)
