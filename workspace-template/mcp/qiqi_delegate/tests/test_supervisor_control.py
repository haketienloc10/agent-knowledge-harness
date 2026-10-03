from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import SessionStore, build_task_packet  # noqa: E402
from supervisor_broker import SupervisorBroker  # noqa: E402
from supervisor_control import (  # noqa: E402
    AutonomousSupervisorRuntime,
    DEFAULT_MODEL,
    HerdrAgentNotReadyError,
    HerdrControlPlane,
    SUPERVISOR_AGENTS,
    SupervisorControlStore,
    build_audit_packet,
    default_supervisor_home,
    parse_supervisor_finding,
    render_lead_finding,
    render_supervisor_prompt,
)


class SupervisorFindingContractTests(unittest.TestCase):
    def test_audit_packet_is_bounded_and_contains_locators_not_raw_evidence(self) -> None:
        case = {
            "case_id": "case-1",
            "rule": "R1",
            "turn_id": "turn-1",
            "work_item_id": "e2e:008",
            "work_item_revision": 3,
            "candidate_id": "sha256:abc",
            "details": {"turn_id": "turn-1"},
        }
        packet = build_audit_packet(case)
        encoded = json.dumps(packet)

        self.assertEqual(packet["version"], 2)
        self.assertEqual(packet["case_id"], "case-1")
        self.assertEqual(
            packet["rule_contract"],
            {
                "predicate": (
                    "An actual Peer response exists for the exact turn and no explicit Lead "
                    "disposition is recorded for that same Peer turn."
                ),
                "issue_when": [
                    "peer_response_locator.turn_id is present",
                    "disposition_state.recorded is false",
                ],
            },
        )
        self.assertEqual(
            packet["lead_brief_locator"],
            {"turn_id": "turn-1", "source": "turns.task_packet_json"},
        )
        self.assertEqual(
            packet["peer_response_locator"],
            {"turn_id": "turn-1", "source": "turns.agent_response"},
        )
        self.assertFalse(packet["disposition_state"]["recorded"])
        self.assertNotIn("agent_response", packet)
        self.assertNotIn("task_packet_json", packet)
        self.assertNotIn("RAW PEER RESPONSE", encoded)

    def test_audit_packet_exposes_normative_contract_for_every_broker_rule(self) -> None:
        cases = {
            "R1": {"turn_id": "turn-r1"},
            "R2": {
                "turn_id": "turn-r2-source",
                "details": {
                    "source_turn_id": "turn-r2-source",
                    "consumer_turn_id": "turn-r2-consumer",
                },
            },
            "R3": {
                "turn_id": None,
                "details": {
                    "claim_ids": ["claim-a", "claim-b"],
                    "overlap_pairs": [{"left": "src", "right": "src/pricing.py"}],
                    "overlap_pairs_truncated": False,
                },
            },
            "R4": {
                "turn_id": "turn-r4",
                "details": {"signal": "BLOCKED"},
            },
            "R5": {
                "turn_id": "turn-r5",
                "details": {"stale_revision": 1, "current_revision": 2},
            },
        }

        for rule, overrides in cases.items():
            with self.subTest(rule=rule):
                case = {
                    "case_id": f"case-{rule}",
                    "rule": rule,
                    "work_item_id": "e2e:contract",
                    "work_item_revision": 2,
                    "candidate_id": None,
                    "details": {},
                    **overrides,
                }
                packet = build_audit_packet(case)
                self.assertEqual(packet["version"], 2)
                self.assertTrue(packet["rule_contract"]["predicate"])
                self.assertTrue(packet["rule_contract"]["issue_when"])

    def test_audit_packet_rejects_unknown_rule_without_guessing(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported Supervisor rule"):
            build_audit_packet(
                {
                    "case_id": "case-unknown",
                    "rule": "R99",
                    "details": {},
                }
            )

    def test_r2_audit_packet_preserves_acceptance_timing(self) -> None:
        packet = build_audit_packet(
            {
                "case_id": "case-r2-temporal",
                "rule": "R2",
                "turn_id": "turn-source",
                "work_item_id": "e2e:r2",
                "work_item_revision": 1,
                "candidate_id": None,
                "details": {
                    "source_turn_id": "turn-source",
                    "consumer_turn_id": "turn-consumer",
                    "consumption_event_seq": 12,
                    "accepted_before_consumption": False,
                },
                "lead_disposition": {
                    "disposition_id": "disp-late",
                    "action": "accept",
                    "event_seq": 15,
                    "work_item_revision": 1,
                    "candidate_id": None,
                },
            }
        )

        self.assertTrue(packet["disposition_state"]["recorded"])
        self.assertEqual(packet["disposition_state"]["action"], "accept")
        self.assertEqual(packet["disposition_state"]["event_seq"], 15)
        self.assertEqual(packet["disposition_state"]["consumption_event_seq"], 12)
        self.assertFalse(
            packet["disposition_state"]["accepted_before_consumption"]
        )
        self.assertFalse(
            packet["disposition_state"]["recorded_before_consumption"]
        )
        self.assertIn(
            "later ACCEPT does not erase the temporal violation",
            packet["rule_contract"]["predicate"],
        )
        self.assertFalse(
            packet["governance_facts"]["accepted_before_consumption"]
        )

    def test_audit_packet_reports_existing_lead_disposition(self) -> None:
        packet = build_audit_packet(
            {
                "case_id": "case-r5",
                "rule": "R5",
                "turn_id": "turn-stale",
                "work_item_id": "e2e:009",
                "work_item_revision": 3,
                "candidate_id": None,
                "details": {
                    "turn_id": "turn-stale",
                    "stale_revision": 2,
                    "current_revision": 3,
                },
                "lead_disposition": {
                    "disposition_id": "disp-1",
                    "action": "accept",
                    "work_item_revision": 2,
                    "candidate_id": "candidate-1",
                },
            }
        )

        self.assertEqual(
            packet["disposition_state"],
            {
                "recorded": True,
                "source": "lead_dispositions",
                "disposition_id": "disp-1",
                "action": "accept",
                "work_item_revision": 2,
                "candidate_id": "candidate-1",
            },
        )

    def test_supervisor_agents_requires_ste_lite_vietnamese_human_output(self) -> None:
        self.assertIn("Viết nội dung dành cho Lead bằng tiếng Việt.", SUPERVISOR_AGENTS)
        self.assertIn("## Quy tắc ngôn ngữ STE-lite", SUPERVISOR_AGENTS)
        self.assertIn("Giữ nguyên technical name và identifier.", SUPERVISOR_AGENTS)
        self.assertIn("`observation`", SUPERVISOR_AGENTS)
        self.assertIn("`evidence`", SUPERVISOR_AGENTS)
        self.assertIn("`open_question_for_lead`", SUPERVISOR_AGENTS)
        self.assertIn(
            "Lead sẽ ghi nhận disposition nào cho Peer response của turn <turn_id>?",
            SUPERVISOR_AGENTS,
        )
        self.assertIn('"status": "issue" | "no_issue"', SUPERVISOR_AGENTS)

    def test_render_supervisor_prompt_repeats_vietnamese_output_contract(self) -> None:
        packet = build_audit_packet(
            {
                "case_id": "case-vi",
                "rule": "R1",
                "turn_id": "turn-vi",
                "work_item_id": "e2e:vi",
                "work_item_revision": 1,
                "candidate_id": None,
                "details": {"turn_id": "turn-vi"},
            }
        )

        prompt = render_supervisor_prompt(packet)

        self.assertIn(
            "Viết observation, từng evidence item và open_question_for_lead bằng tiếng Việt",
            prompt,
        )
        self.assertIn("theo STE-lite", prompt)
        self.assertIn(
            "Giữ nguyên JSON field, enum, rule id, technical name và identifier.",
            prompt,
        )
        self.assertIn(
            "open_question_for_lead phải là đúng một câu hỏi tiếng Việt",
            prompt,
        )
        packet_json = prompt.split("AuditPacket:\n", 1)[1]
        self.assertEqual(json.loads(packet_json), packet)
        self.assertIn(
            "An actual Peer response exists for the exact turn",
            packet["rule_contract"]["predicate"],
        )

    def test_finding_schema_accepts_governance_only_issue(self) -> None:
        finding = parse_supervisor_finding(
            json.dumps(
                {
                    "case_id": "case-1",
                    "status": "issue",
                    "observation": (
                        "Đã có Peer response cho turn turn-1. "
                        "Lead chưa ghi nhận disposition cho turn này."
                    ),
                    "evidence": [
                        "peer_response_locator.turn_id có giá trị turn-1.",
                        "disposition_state.recorded là false.",
                    ],
                    "open_question_for_lead": (
                        "Lead sẽ ghi nhận disposition nào cho Peer response của turn turn-1?"
                    ),
                },
                ensure_ascii=False,
            ),
            expected_case_id="case-1",
        )
        self.assertEqual(finding["status"], "issue")
        self.assertIn("Lead sẽ ghi nhận disposition nào", finding["open_question_for_lead"])

    def test_finding_schema_accepts_no_issue_without_lead_question(self) -> None:
        finding = parse_supervisor_finding(
            json.dumps(
                {
                    "case_id": "case-2",
                    "status": "no_issue",
                    "observation": "The bounded facts do not establish a governance deviation.",
                    "evidence": ["bounded packet is internally consistent"],
                    "open_question_for_lead": None,
                }
            ),
            expected_case_id="case-2",
        )
        self.assertEqual(finding["status"], "no_issue")

    def test_finding_schema_rejects_technical_action_or_delegation_fields(self) -> None:
        for forbidden in ("action", "decision", "delegation", "patch", "tool_call"):
            payload = {
                "case_id": "case-1",
                "status": "issue",
                "observation": "Governance gap.",
                "evidence": ["evidence"],
                "open_question_for_lead": "What closes this gap?",
                forbidden: "ACCEPT",
            }
            with self.subTest(forbidden=forbidden):
                with self.assertRaisesRegex(ValueError, "schema mismatch"):
                    parse_supervisor_finding(
                        json.dumps(payload),
                        expected_case_id="case-1",
                    )

    def test_lead_message_is_advisory_and_has_no_executable_action(self) -> None:
        message = render_lead_finding(
            {
                "case_id": "case-1",
                "status": "issue",
                "observation": "The communication loop is incomplete.",
                "evidence": ["turn-1 has no disposition"],
                "open_question_for_lead": "What disposition closes turn-1?",
            }
        )
        self.assertIn("oversight finding", message)
        self.assertIn("not technical acceptance/rejection", message)
        self.assertNotIn("delegate_repo_task", message)
        self.assertNotIn("record_lead_disposition(", message)

    def test_lead_message_includes_exact_runtime_locator(self) -> None:
        message = render_lead_finding(
            {
                "case_id": "case-locator",
                "status": "issue",
                "observation": "The loop is incomplete.",
                "evidence": ["disposition_state.recorded=false"],
                "open_question_for_lead": "What explicit disposition closes this turn?",
                "_case_context": {
                    "turn_id": "turn-exact",
                    "work_item_id": "e2e:008",
                    "work_item_revision": 7,
                    "candidate_id": "sha256:exact",
                },
            }
        )
        self.assertIn("peer_turn_id: turn-exact", message)
        self.assertIn("work_item: e2e:008@7", message)
        self.assertIn("candidate_id: sha256:exact", message)

        r2_message = render_lead_finding(
            {
                "case_id": "case-r2-locator",
                "status": "issue",
                "observation": "Dependency was consumed before acceptance.",
                "evidence": ["temporal R2 evidence"],
                "open_question_for_lead": "How was the downstream premise remediated?",
                "_case_context": {"consumption_event_seq": 42},
            }
        )
        self.assertIn("consumption_event_seq: 42", r2_message)

        r3_message = render_lead_finding(
            {
                "case_id": "case-r3-locator",
                "status": "issue",
                "observation": "Repository write scopes overlap.",
                "evidence": ["two durable claims are active"],
                "open_question_for_lead": "Which abandoned claim should be released?",
                "_case_context": {
                    "repository": "repo-a",
                    "claim_ids": [
                        "repo:repo-a:turn:one",
                        "repo:repo-a:turn:two",
                    ],
                },
            }
        )
        self.assertIn("repository: repo-a", r3_message)
        self.assertIn("write_claim_id: repo:repo-a:turn:one", r3_message)
        self.assertIn("write_claim_id: repo:repo-a:turn:two", r3_message)

    def test_default_supervisor_home_is_outside_workspace_project_tree(self) -> None:
        workspace = Path("/tmp/project/workspace")
        home = default_supervisor_home(
            workspace,
            environ={"HOME": "/tmp/control-user"},
        )
        self.assertTrue(str(home).startswith("/tmp/control-user/.local/state/qiqi-supervisor/"))
        self.assertFalse(str(home).startswith(str(workspace)))


class _FakeControlPlane:
    def __init__(self, finding_status: str):
        self.finding_status = finding_status
        self.ensure_calls = 0
        self.supervisor_packets: list[dict] = []
        self.lead_findings: list[dict] = []

    async def ensure_started(self):
        self.ensure_calls += 1
        return {"workspace_id": "w1"}

    async def prompt_supervisor(self, packet):
        self.supervisor_packets.append(packet)
        if self.finding_status == "issue":
            return {
                "case_id": packet["case_id"],
                "status": "issue",
                "observation": "Peer response exists without Lead disposition.",
                "evidence": ["disposition_state.recorded=false"],
                "open_question_for_lead": "What explicit disposition closes this response?",
            }
        return {
            "case_id": packet["case_id"],
            "status": "no_issue",
            "observation": "Bounded evidence does not establish an issue.",
            "evidence": ["packet checked"],
            "open_question_for_lead": None,
        }

    async def wake_lead(self, finding):
        self.lead_findings.append(finding)


class AutonomousSupervisorRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp.name) / "qiqi_delegate.sqlite3"
        self.store = SessionStore(self.db_path)
        self.broker = SupervisorBroker(self.db_path)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _record_turn(self, turn_id: str) -> None:
        packet = build_task_packet(
            objective="Produce one bounded result.",
            scope=["repository work"],
            acceptance_criteria=["focused verification passes"],
        )
        self.store.record_turn(
            turn_id=turn_id,
            session_id=f"session-{turn_id}",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=packet,
            agent_response="raw peer response",
        )

    async def test_confirmed_issue_wakes_lead_but_ack_delivery_does_not_close_case(self) -> None:
        self._record_turn("turn-1")
        self.broker.process_pending()
        fake = _FakeControlPlane("issue")
        runtime = AutonomousSupervisorRuntime(
            state_db=self.db_path,
            control_plane=fake,
        )

        result = await runtime.handle_pending_cases()

        self.assertEqual(
            result,
            {
                "reviewed": 1,
                "delivered_to_lead": 1,
                "review_attempted": 1,
                "delivery_attempted": 1,
                "review_failures": 0,
                "delivery_failures": 0,
            },
        )
        self.assertEqual(len(fake.supervisor_packets), 1)
        self.assertEqual(len(fake.lead_findings), 1)
        self.assertEqual(
            fake.lead_findings[0]["_case_context"]["turn_id"],
            "turn-1",
        )
        case = self.broker.list_cases()[0]
        self.assertEqual(case["status"], "WAITING_FOR_EVIDENCE")
        self.assertIsNone(case["closed_event_seq"])

        # Herdr delivery/Lead acknowledgement has no semantic closure effect.
        self.broker.process_pending()
        case = self.broker.list_cases()[0]
        self.assertEqual(case["status"], "WAITING_FOR_EVIDENCE")

        self.store.record_lead_disposition(
            turn_id="turn-1",
            action="accept",
            reason="Lead independently reviewed the candidate",
        )
        self.broker.process_pending()
        self.assertEqual(self.broker.list_cases()[0]["status"], "CLOSED")

    async def test_r2_runtime_packet_keeps_late_accept_temporally_invalid(self) -> None:
        self._record_turn("turn-r2-temporal")
        self.store.record_slp_event(
            event_type="dependency.consumed",
            turn_id="turn-r2-consumer",
            repository="repo-b",
            payload={"source_turn_id": "turn-r2-temporal"},
        )
        self.store.record_lead_disposition(
            turn_id="turn-r2-temporal",
            action="accept",
            reason="accepted only after downstream consumption",
        )
        self.broker.process_pending()

        fake = _FakeControlPlane("issue")
        runtime = AutonomousSupervisorRuntime(
            state_db=self.db_path,
            control_plane=fake,
        )
        await runtime.handle_pending_cases(deliver=False)

        r2_packets = [
            packet for packet in fake.supervisor_packets if packet["rule"] == "R2"
        ]
        self.assertEqual(len(r2_packets), 1)
        packet = r2_packets[0]
        self.assertEqual(packet["disposition_state"]["action"], "accept")
        self.assertFalse(
            packet["disposition_state"]["accepted_before_consumption"]
        )
        self.assertFalse(
            packet["disposition_state"]["recorded_before_consumption"]
        )
        self.assertGreater(
            packet["disposition_state"]["event_seq"],
            packet["disposition_state"]["consumption_event_seq"],
        )
        pending = SupervisorControlStore(
            self.db_path
        ).issue_findings_needing_delivery()
        self.assertEqual(len(pending), 1)
        self.assertEqual(
            pending[0]["_case_context"]["consumption_event_seq"],
            packet["disposition_state"]["consumption_event_seq"],
        )

    async def test_r3_delivery_context_hydrates_claim_recovery_locators(self) -> None:
        self.store.record_write_scope_claim(
            claim_id="repo:repo-a:turn:r3-one",
            repository="repo-a",
            owner="r3-one",
            scope=["*"],
            turn_id="r3-one",
        )
        self.store.record_write_scope_claim(
            claim_id="repo:repo-a:turn:r3-two",
            repository="repo-a",
            owner="r3-two",
            scope=["*"],
            turn_id="r3-two",
        )
        self.broker.process_pending()

        fake = _FakeControlPlane("issue")
        runtime = AutonomousSupervisorRuntime(
            state_db=self.db_path,
            control_plane=fake,
        )
        await runtime.handle_pending_cases(deliver=False)

        pending = SupervisorControlStore(
            self.db_path
        ).issue_findings_needing_delivery()
        self.assertEqual(len(pending), 1)
        context = pending[0]["_case_context"]
        self.assertEqual(context["repository"], "repo-a")
        self.assertEqual(
            sorted(context["claim_ids"]),
            [
                "repo:repo-a:turn:r3-one",
                "repo:repo-a:turn:r3-two",
            ],
        )

    async def test_r5_runtime_packet_hydrates_prior_lead_disposition(self) -> None:
        packet = build_task_packet(
            objective="Produce one bounded result.",
            scope=["repository work"],
            acceptance_criteria=["focused verification passes"],
            context={
                "trusted_facts": [
                    {
                        "fact": (
                            "work_item_path=/tmp/work-items/e2e:010; "
                            "id=e2e:010; revision=2"
                        ),
                        "source": "canonical Work Item locator",
                    }
                ]
            },
        )
        self.store.record_turn(
            turn_id="turn-r5-accepted",
            session_id="session-turn-r5-accepted",
            repository="repo-a",
            agent="claude",
            route="claude-balanced",
            state="settled",
            native_turn_id=None,
            packet=packet,
            agent_response="raw peer response",
        )
        self.broker.process_pending()
        self.store.record_lead_disposition(
            turn_id="turn-r5-accepted",
            action="accept",
            reason="candidate met revision 2 requirements",
            work_item_id="e2e:010",
            work_item_revision=2,
            candidate_id="candidate-r2",
        )
        self.broker.process_pending()
        self.store.record_slp_event(
            event_type="work_item.revision_changed",
            work_item_id="e2e:010",
            work_item_revision=3,
            payload={"reason": "material requirement change"},
        )
        self.broker.process_pending()

        fake = _FakeControlPlane("no_issue")
        runtime = AutonomousSupervisorRuntime(
            state_db=self.db_path,
            control_plane=fake,
        )
        await runtime.handle_pending_cases()

        self.assertEqual(len(fake.supervisor_packets), 1)
        self.assertEqual(fake.supervisor_packets[0]["rule"], "R5")
        self.assertEqual(
            fake.supervisor_packets[0]["disposition_state"],
            {
                "recorded": True,
                "source": "lead_dispositions",
                "disposition_id": self.store.get_lead_disposition(
                    "turn-r5-accepted"
                )["disposition_id"],
                "action": "accept",
                "work_item_revision": 2,
                "candidate_id": "candidate-r2",
            },
        )

    async def test_runtime_isolates_one_failed_supervisor_case(self) -> None:
        self._record_turn("turn-fail")
        self._record_turn("turn-ok")
        self.broker.process_pending()

        class PartialFailure(_FakeControlPlane):
            def __init__(self):
                super().__init__("issue")
                self.calls = 0

            async def prompt_supervisor(self, packet):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("transient supervisor failure")
                return await super().prompt_supervisor(packet)

        fake = PartialFailure()
        runtime = AutonomousSupervisorRuntime(
            state_db=self.db_path,
            control_plane=fake,
        )
        result = await runtime.handle_pending_cases()

        self.assertEqual(result["review_failures"], 1)
        self.assertIn("transient supervisor failure", result["last_error"])
        self.assertIn("review case", result["last_error"])
        self.assertEqual(result["reviewed"], 1)
        self.assertEqual(result["delivered_to_lead"], 1)
        self.assertEqual(
            len(SupervisorControlStore(self.db_path).pending_unreviewed_cases()),
            1,
        )

    async def test_delivery_replays_closure_committed_after_finding_selection(
        self,
    ) -> None:
        self._record_turn("turn-delivery-race")
        self.broker.process_pending()
        fake = _FakeControlPlane("issue")
        runtime = AutonomousSupervisorRuntime(
            state_db=self.db_path,
            control_plane=fake,
        )
        await runtime.handle_pending_cases(deliver=False)
        self.assertEqual(len(fake.lead_findings), 0)

        replay_calls = 0

        async def replay_before_delivery() -> None:
            nonlocal replay_calls
            replay_calls += 1
            if replay_calls == 1:
                self.store.record_lead_disposition(
                    turn_id="turn-delivery-race",
                    action="reject",
                    reason="Lead resolved the case before Supervisor delivery",
                )
            self.broker.process_pending()

        result = await runtime.handle_pending_cases(
            review=False,
            deliver=True,
            before_delivery=replay_before_delivery,
        )

        self.assertEqual(result["delivery_attempted"], 1)
        self.assertEqual(result["delivered_to_lead"], 0)
        self.assertEqual(fake.lead_findings, [])
        self.assertEqual(
            self.broker.list_cases()[0]["status"],
            "CLOSED",
        )

    async def test_delivery_guard_rejects_unreplayed_closure_evidence(self) -> None:
        self._record_turn("turn-unreplayed-closure")
        self.broker.process_pending()
        fake = _FakeControlPlane("issue")
        runtime = AutonomousSupervisorRuntime(
            state_db=self.db_path,
            control_plane=fake,
        )
        await runtime.handle_pending_cases(deliver=False)

        # Simulate a Lead closure committed after the last broker replay but before
        # notification selection. The materialized case row is still OPEN here.
        self.store.record_lead_disposition(
            turn_id="turn-unreplayed-closure",
            action="reject",
            reason="Lead resolved this turn before the wakeup was selected",
        )
        self.assertEqual(self.broker.list_cases()[0]["status"], "OPEN")

        async def no_op_replay() -> None:
            return None

        result = await runtime.handle_pending_cases(
            review=False,
            deliver=True,
            before_delivery=no_op_replay,
        )

        self.assertEqual(result["delivery_attempted"], 1)
        self.assertEqual(result["delivered_to_lead"], 0)
        self.assertEqual(fake.lead_findings, [])

        self.broker.process_pending()
        self.assertEqual(self.broker.list_cases()[0]["status"], "CLOSED")

    async def test_runtime_is_idempotent_after_finding_delivery(self) -> None:
        self._record_turn("turn-2")
        self.broker.process_pending()
        fake = _FakeControlPlane("issue")
        runtime = AutonomousSupervisorRuntime(
            state_db=self.db_path,
            control_plane=fake,
        )

        await runtime.handle_pending_cases()
        second = await runtime.handle_pending_cases()

        self.assertEqual(
            second,
            {
                "reviewed": 0,
                "delivered_to_lead": 0,
                "review_attempted": 0,
                "delivery_attempted": 0,
                "review_failures": 0,
                "delivery_failures": 0,
            },
        )
        self.assertEqual(len(fake.supervisor_packets), 1)
        self.assertEqual(len(fake.lead_findings), 1)

    async def test_no_issue_is_recorded_without_waking_lead_or_closing_from_opinion(self) -> None:
        self._record_turn("turn-3")
        self.broker.process_pending()
        fake = _FakeControlPlane("no_issue")
        runtime = AutonomousSupervisorRuntime(
            state_db=self.db_path,
            control_plane=fake,
        )

        result = await runtime.handle_pending_cases()

        self.assertEqual(
            result,
            {
                "reviewed": 1,
                "delivered_to_lead": 0,
                "review_attempted": 1,
                "delivery_attempted": 0,
                "review_failures": 0,
                "delivery_failures": 0,
            },
        )
        self.assertEqual(fake.lead_findings, [])
        case = self.broker.list_cases()[0]
        self.assertEqual(case["status"], "WAITING_FOR_EVIDENCE")
        self.assertIsNone(case["closed_event_seq"])

        control_store = SupervisorControlStore(self.db_path)
        self.assertEqual(control_store.issue_findings_needing_delivery(), [])


class _RecordingHerdrControlPlane(HerdrControlPlane):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.commands: list[tuple[str, ...]] = []
        self.command_sessions: list[str | None] = []
        self.agent_names: set[str] = set()
        self.agent_panes: dict[str, str] = {}

    async def _ensure_server(self) -> None:
        return None

    async def _agent_info(self, name: str):
        if name not in self.agent_names:
            return None
        return {
            "name": name,
            "pane_id": self.agent_panes.get(
                name, "w-control:p1" if name == "lead" else "w-control:p2"
            ),
            "interactive_ready": True,
            "agent_status": "idle",
            "launch_pending": False,
        }

    async def _run(
        self,
        *args: str,
        check: bool = True,
        session: str | None = None,
    ):
        self.commands.append(tuple(args))
        self.command_sessions.append(session)
        if len(args) >= 3 and args[:2] == ("agent", "start"):
            self.agent_names.add(args[2])
            pane_index = args.index("--pane") + 1
            self.agent_panes[args[2]] = args[pane_index]
        if args[:2] == ("workspace", "close"):
            self.agent_names.clear()
            self.agent_panes.clear()
        return 0, "{}", ""

    async def _run_json(self, *args: str, session: str | None = None):
        self.commands.append(tuple(args))
        self.command_sessions.append(session)
        if args[:2] == ("workspace", "create"):
            return {
                "result": {
                    "workspace": {"workspace_id": "w-control"},
                    "root_pane": {"pane_id": "w-control:p1"},
                }
            }
        if args[:2] == ("pane", "split"):
            return {"result": {"pane": {"pane_id": "w-control:p2"}}}
        raise AssertionError(f"unexpected JSON command: {args!r}")


class _MissingPersistedPaneControlPlane(_RecordingHerdrControlPlane):
    async def _run(
        self,
        *args: str,
        check: bool = True,
        session: str | None = None,
    ):
        if args[:3] == ("pane", "get", "w-old:p1"):
            self.commands.append(tuple(args))
            return 1, "", "pane not found"
        return await super()._run(*args, check=check, session=session)


class _StaleNamedAgentControlPlane(_RecordingHerdrControlPlane):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.agent_names.update({"lead", "supervisor"})
        self.ready = False

    async def _agent_info(self, name: str):
        if name not in self.agent_names:
            return None
        return {
            "name": name,
            "pane_id": "w-control:p1" if name == "lead" else "w-control:p2",
            "interactive_ready": self.ready,
            "agent_status": "idle" if self.ready else "unknown",
            "launch_pending": not self.ready,
        }

    async def _run(
        self,
        *args: str,
        check: bool = True,
        session: str | None = None,
    ):
        result = await super()._run(*args, check=check, session=session)
        if args[:2] == ("workspace", "close"):
            # The recreated control room starts fresh agents that can become ready.
            self.ready = True
        return result

    async def _wait_agent_prompt_ready(self, name: str, *, timeout_ms: int = 60_000):
        if not self.ready:
            raise HerdrAgentNotReadyError(
                f"stale named agent is not prompt-ready: {name}"
            )
        return await super()._wait_agent_prompt_ready(name, timeout_ms=timeout_ms)


class _AbruptAfterLeadStartControlPlane(_RecordingHerdrControlPlane):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.crash_once = True

    async def _start_agent(
        self,
        name: str,
        pane_id: str,
        args: list[str],
    ) -> None:
        await super()._start_agent(name, pane_id, args)
        if name == "lead" and self.crash_once:
            self.crash_once = False
            raise KeyboardInterrupt("simulated process termination after lead start")


class _PartialCreateFailureControlPlane(_RecordingHerdrControlPlane):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fail_supervisor_once = True

    async def _start_agent(
        self,
        name: str,
        pane_id: str,
        args: list[str],
    ) -> None:
        if name == "supervisor" and self.fail_supervisor_once:
            self.fail_supervisor_once = False
            raise RuntimeError("simulated supervisor start failure")
        await super()._start_agent(name, pane_id, args)


class _CleanupFailureControlPlane(_PartialCreateFailureControlPlane):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.fail_close_once = True

    async def _run(
        self,
        *args: str,
        check: bool = True,
        session: str | None = None,
    ):
        if args[:2] == ("workspace", "close") and self.fail_close_once:
            self.fail_close_once = False
            self.commands.append(tuple(args))
            self.command_sessions.append(session)
            return 1, "", "simulated close failure"
        return await super()._run(*args, check=check, session=session)


class HerdrControlPlaneCommandTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_session_is_namespaced_by_workspace_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace_a = root / "workspace-a"
            workspace_b = root / "workspace-b"
            workspace_a.mkdir()
            workspace_b.mkdir()
            control_a = HerdrControlPlane(
                workspace_root=workspace_a,
                state_db=workspace_a / ".qiqi" / "state" / "qiqi_delegate.sqlite3",
                supervisor_home=root / "supervisor-a",
            )
            control_b = HerdrControlPlane(
                workspace_root=workspace_b,
                state_db=workspace_b / ".qiqi" / "state" / "qiqi_delegate.sqlite3",
                supervisor_home=root / "supervisor-b",
            )
            explicit = HerdrControlPlane(
                workspace_root=workspace_b,
                state_db=workspace_b / ".qiqi" / "state" / "explicit.sqlite3",
                supervisor_home=root / "supervisor-explicit",
                session="shared-by-user-choice",
            )

            self.assertNotEqual(control_a.session, control_b.session)
            self.assertTrue(control_a.session.startswith("qiqi-delegate-"))
            self.assertTrue(control_b.session.startswith("qiqi-delegate-"))
            self.assertEqual(explicit.session, "shared-by-user-choice")

    async def test_cli_command_timeout_terminates_stalled_process(self) -> None:
        class HangingProcess:
            def __init__(self):
                self.returncode = None
                self.terminated = False
                self.killed = False
                self.release = asyncio.Event()

            async def communicate(self):
                await self.release.wait()
                return b"", b""

            def terminate(self):
                self.terminated = True
                self.returncode = -15
                self.release.set()

            def kill(self):
                self.killed = True
                self.returncode = -9
                self.release.set()

            async def wait(self):
                return self.returncode

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            process = HangingProcess()
            control = HerdrControlPlane(
                workspace_root=workspace,
                state_db=workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3",
                supervisor_home=root / "isolated-supervisor",
                command_timeout_seconds=0.01,
            )
            with patch(
                "supervisor_control.asyncio.create_subprocess_exec",
                new=AsyncMock(return_value=process),
            ):
                with self.assertRaisesRegex(RuntimeError, "Herdr command timed out"):
                    await control._run("status", "server")

            self.assertTrue(process.terminated)
            self.assertFalse(process.killed)

    async def test_declared_herdr_timeout_extends_outer_command_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            control = HerdrControlPlane(
                workspace_root=workspace,
                state_db=workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3",
                supervisor_home=root / "isolated-supervisor",
                command_timeout_seconds=0.01,
            )

            self.assertGreaterEqual(
                control._outer_command_timeout(
                    (
                        "agent",
                        "prompt",
                        "supervisor",
                        "review",
                        "--wait",
                        "--timeout",
                        "120000",
                    )
                ),
                121.0,
            )
            self.assertGreaterEqual(
                control._outer_command_timeout(
                    ("agent", "start", "lead", "--timeout", "60000")
                ),
                61.0,
            )


class HerdrControlPlaneTopologyTests(unittest.IsolatedAsyncioTestCase):
    async def test_provisional_topology_survives_abrupt_agent_start_termination(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            state_db = workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            control = _AbruptAfterLeadStartControlPlane(
                workspace_root=workspace,
                state_db=state_db,
                supervisor_home=root / "isolated-supervisor",
            )

            with self.assertRaisesRegex(
                KeyboardInterrupt,
                "simulated process termination",
            ):
                await control.ensure_started()

            provisional = control.store.get_control_plane()
            self.assertIsNotNone(provisional)
            self.assertEqual(provisional["workspace_id"], "w-control")
            self.assertEqual(provisional["lead_pane_id"], "w-control:p1")
            self.assertEqual(provisional["supervisor_pane_id"], "w-control:p2")

            recovered = await control.ensure_started()
            self.assertEqual(recovered["workspace_id"], "w-control")
            self.assertIn("lead", control.agent_names)
            self.assertIn("supervisor", control.agent_names)

    async def test_failed_partial_cleanup_retains_provisional_topology(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            state_db = workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            control = _CleanupFailureControlPlane(
                workspace_root=workspace,
                state_db=state_db,
                supervisor_home=root / "isolated-supervisor",
            )

            with self.assertRaisesRegex(
                RuntimeError,
                "failed to clean up partially created slp-control workspace",
            ):
                await control.ensure_started()

            provisional = control.store.get_control_plane()
            self.assertIsNotNone(provisional)
            self.assertEqual(provisional["workspace_id"], "w-control")
            self.assertEqual(provisional["lead_pane_id"], "w-control:p1")
            self.assertEqual(provisional["supervisor_pane_id"], "w-control:p2")

            recovered = await control.ensure_started()
            self.assertEqual(recovered["workspace_id"], "w-control")

    async def test_old_session_topology_is_closed_in_stored_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            state_db = workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            supervisor_home = root / "isolated-supervisor"
            control = _RecordingHerdrControlPlane(
                workspace_root=workspace,
                state_db=state_db,
                supervisor_home=supervisor_home,
                session="new-session",
            )
            control.agent_names.update({"lead", "supervisor"})
            control.store.save_control_plane(
                workspace_id="w-old",
                lead_pane_id="w-old:p1",
                supervisor_pane_id="w-old:p2",
                herdr_session="old-session",
                lead_model=DEFAULT_MODEL,
                supervisor_model=DEFAULT_MODEL,
                supervisor_home=supervisor_home,
                supervisor_capture_dir=supervisor_home / "captures",
                supervisor_capture_nonce="old-nonce",
            )

            state = await control.ensure_started()

            close_index = control.commands.index(("workspace", "close", "w-old"))
            self.assertEqual(control.command_sessions[close_index], "old-session")
            self.assertEqual(state["herdr_session"], "new-session")

    async def test_partial_initial_creation_is_closed_before_retry(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            state_db = workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            control = _PartialCreateFailureControlPlane(
                workspace_root=workspace,
                state_db=state_db,
                supervisor_home=root / "isolated-supervisor",
            )

            with self.assertRaisesRegex(RuntimeError, "simulated supervisor start failure"):
                await control.ensure_started()

            self.assertIsNone(control.store.get_control_plane())
            self.assertIn(("workspace", "close", "w-control"), control.commands)
            self.assertEqual(control.agent_names, set())

            state = await control.ensure_started()
            self.assertEqual(state["workspace_id"], "w-control")
            self.assertEqual(state["lead_agent_name"], "lead")
            self.assertEqual(state["supervisor_agent_name"], "supervisor")

    async def test_missing_persisted_pane_recreates_control_room(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            state_db = workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            supervisor_home = root / "isolated-supervisor"
            control = _MissingPersistedPaneControlPlane(
                workspace_root=workspace,
                state_db=state_db,
                supervisor_home=supervisor_home,
            )
            control.store.save_control_plane(
                workspace_id="w-old",
                lead_pane_id="w-old:p1",
                supervisor_pane_id="w-old:p2",
                herdr_session=control.session,
                lead_model=DEFAULT_MODEL,
                supervisor_model=DEFAULT_MODEL,
                supervisor_home=supervisor_home,
                supervisor_capture_dir=supervisor_home / "captures",
                supervisor_capture_nonce="old-nonce",
            )

            state = await control.ensure_started()

            self.assertEqual(state["workspace_id"], "w-control")
            self.assertEqual(state["lead_pane_id"], "w-control:p1")
            self.assertEqual(state["supervisor_pane_id"], "w-control:p2")
            self.assertIn(("workspace", "close", "w-old"), control.commands)
            self.assertTrue(
                any(command[:3] == ("agent", "start", "lead") for command in control.commands)
            )
            self.assertTrue(
                any(
                    command[:3] == ("agent", "start", "supervisor")
                    for command in control.commands
                )
            )

    async def test_model_identity_change_recreates_control_room(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            state_db = workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            supervisor_home = root / "isolated-supervisor"
            control = _RecordingHerdrControlPlane(
                workspace_root=workspace,
                state_db=state_db,
                supervisor_home=supervisor_home,
            )
            control.agent_names.update({"lead", "supervisor"})
            control.store.save_control_plane(
                workspace_id="w-old",
                lead_pane_id="w-old:p1",
                supervisor_pane_id="w-old:p2",
                herdr_session=control.session,
                lead_model="gpt-5.4",
                supervisor_model="gpt-5.4",
                supervisor_home=supervisor_home,
                supervisor_capture_dir=supervisor_home / "captures",
                supervisor_capture_nonce="old-nonce",
            )

            state = await control.ensure_started()

            self.assertEqual(state["lead_model"], "gpt-5.6-luna")
            self.assertEqual(state["supervisor_model"], "gpt-5.6-luna")
            self.assertIn(
                ("workspace", "close", "w-old"),
                control.commands,
            )
            self.assertTrue(
                any(
                    command[:3] == ("agent", "start", "lead")
                    and "gpt-5.6-luna" in command
                    for command in control.commands
                )
            )
            self.assertTrue(
                any(
                    command[:3] == ("agent", "start", "supervisor")
                    and "gpt-5.6-luna" in command
                    for command in control.commands
                )
            )

    async def test_stale_same_pane_agents_recreate_control_room(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            state_db = workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            control = _StaleNamedAgentControlPlane(
                workspace_root=workspace,
                state_db=state_db,
                supervisor_home=root / "isolated-supervisor",
            )
            control.store.save_control_plane(
                workspace_id="w-control",
                lead_pane_id="w-control:p1",
                supervisor_pane_id="w-control:p2",
                herdr_session=control.session,
                lead_model=DEFAULT_MODEL,
                supervisor_model=DEFAULT_MODEL,
                supervisor_home=root / "isolated-supervisor",
                supervisor_capture_dir=root / "isolated-supervisor" / "captures",
                supervisor_capture_nonce="nonce",
            )

            state = await control.ensure_started()

            self.assertEqual(state["workspace_id"], "w-control")
            self.assertIn(("workspace", "close", "w-control"), control.commands)
            self.assertTrue(
                any(command[:3] == ("agent", "start", "lead") for command in control.commands)
            )
            self.assertTrue(
                any(
                    command[:3] == ("agent", "start", "supervisor")
                    for command in control.commands
                )
            )

    async def test_prompt_ready_named_agent_on_wrong_pane_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            state_db = workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            control = _RecordingHerdrControlPlane(
                workspace_root=workspace,
                state_db=state_db,
                supervisor_home=root / "isolated-supervisor",
            )
            control.agent_names.update({"lead", "supervisor"})
            control.agent_panes.update(
                {"lead": "wrong:p1", "supervisor": "wrong:p2"}
            )
            control.store.save_control_plane(
                workspace_id="w-control",
                lead_pane_id="w-control:p1",
                supervisor_pane_id="w-control:p2",
                herdr_session=control.session,
                lead_model=DEFAULT_MODEL,
                supervisor_model=DEFAULT_MODEL,
                supervisor_home=root / "isolated-supervisor",
                supervisor_capture_dir=root / "isolated-supervisor" / "captures",
                supervisor_capture_nonce="nonce",
            )

            with self.assertRaisesRegex(RuntimeError, "topology mismatch"):
                await control.ensure_started()

    def test_launcher_does_not_force_global_herdr_session(self) -> None:
        launcher = (
            Path(__file__).resolve().parents[3]
            / "scripts"
            / "qiqi-supervisor-broker.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            'QIQI_HERDR_SESSION="${QIQI_HERDR_SESSION:-qiqi-delegate}"',
            launcher,
        )
        self.assertIn("supervisor_broker.py derives the default", launcher)

    def test_live_e2e_uses_same_workspace_scoped_session_default(self) -> None:
        script = (
            Path(__file__).resolve().parents[3]
            / "scripts"
            / "e2e-autonomous-supervisor.sh"
        ).read_text(encoding="utf-8")
        self.assertNotIn(
            'session="${QIQI_HERDR_SESSION:-qiqi-delegate}"',
            script,
        )
        self.assertIn("hashlib.sha256", script)
        self.assertIn('print(f"qiqi-delegate-{digest}")', script)

    async def test_control_room_starts_independent_lead_and_read_only_supervisor(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            workspace = root / "workspace"
            workspace.mkdir()
            state_db = workspace / ".qiqi" / "state" / "qiqi_delegate.sqlite3"
            supervisor_home = root / "isolated-supervisor"
            control = _RecordingHerdrControlPlane(
                workspace_root=workspace,
                state_db=state_db,
                supervisor_home=supervisor_home,
            )

            state = await control.ensure_started()

            self.assertEqual(state["workspace_id"], "w-control")
            self.assertEqual(state["lead_agent_name"], "lead")
            self.assertEqual(state["supervisor_agent_name"], "supervisor")
            self.assertEqual(state["lead_model"], "gpt-5.6-luna")
            self.assertEqual(state["supervisor_model"], "gpt-5.6-luna")
            self.assertEqual(Path(state["supervisor_home"]), supervisor_home.resolve())
            self.assertTrue((supervisor_home / "AGENTS.md").is_file())

            workspace_create = next(
                command
                for command in control.commands
                if command[:2] == ("workspace", "create")
            )
            self.assertIn(str(workspace.resolve()), workspace_create)

            split = next(
                command
                for command in control.commands
                if command[:2] == ("pane", "split")
            )
            self.assertIn(str(supervisor_home.resolve()), split)

            lead_start = next(
                command
                for command in control.commands
                if command[:3] == ("agent", "start", "lead")
            )
            supervisor_start = next(
                command
                for command in control.commands
                if command[:3] == ("agent", "start", "supervisor")
            )
            self.assertIn("--dangerously-bypass-approvals-and-sandbox", lead_start)
            self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", supervisor_start)
            self.assertIn("--sandbox", supervisor_start)
            self.assertIn("read-only", supervisor_start)
            self.assertIn("--ask-for-approval", supervisor_start)
            self.assertIn("never", supervisor_start)
            self.assertIn("gpt-5.6-luna", lead_start)
            self.assertIn("gpt-5.6-luna", supervisor_start)

            encoded = "\n".join(" ".join(command) for command in control.commands)
            self.assertNotIn("delegate_repo_task", encoded)
            self.assertNotIn("record_lead_disposition", encoded)
            self.assertNotIn("pane read", encoded)
            self.assertNotIn("agent read", encoded)


if __name__ == "__main__":
    unittest.main()
