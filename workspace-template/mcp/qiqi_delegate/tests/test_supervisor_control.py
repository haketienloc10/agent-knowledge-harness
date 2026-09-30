from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core import SessionStore, build_task_packet  # noqa: E402
from supervisor_broker import SupervisorBroker  # noqa: E402
from supervisor_control import (  # noqa: E402
    AutonomousSupervisorRuntime,
    HerdrControlPlane,
    SupervisorControlStore,
    build_audit_packet,
    default_supervisor_home,
    parse_supervisor_finding,
    render_lead_finding,
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

        self.assertEqual(packet["case_id"], "case-1")
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

    def test_finding_schema_accepts_governance_only_issue(self) -> None:
        finding = parse_supervisor_finding(
            json.dumps(
                {
                    "case_id": "case-1",
                    "status": "issue",
                    "observation": "A Peer response exists without a recorded disposition.",
                    "evidence": [
                        "peer_response_locator.turn_id=turn-1",
                        "disposition_state.recorded=false",
                    ],
                    "open_question_for_lead": (
                        "What Lead disposition closes this response before dependent work proceeds?"
                    ),
                }
            ),
            expected_case_id="case-1",
        )
        self.assertEqual(finding["status"], "issue")

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

        self.assertEqual(result, {"reviewed": 1, "delivered_to_lead": 1})
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

        self.assertEqual(second, {"reviewed": 0, "delivered_to_lead": 0})
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

        self.assertEqual(result, {"reviewed": 1, "delivered_to_lead": 0})
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
        self.agent_names: set[str] = set()

    async def _ensure_server(self) -> None:
        return None

    async def _agent_exists(self, name: str) -> bool:
        return name in self.agent_names

    async def _run(self, *args: str, check: bool = True):
        self.commands.append(tuple(args))
        if len(args) >= 3 and args[:2] == ("agent", "start"):
            self.agent_names.add(args[2])
        return 0, "{}", ""

    async def _run_json(self, *args: str):
        self.commands.append(tuple(args))
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


class HerdrControlPlaneTopologyTests(unittest.IsolatedAsyncioTestCase):
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

            encoded = "\n".join(" ".join(command) for command in control.commands)
            self.assertNotIn("delegate_repo_task", encoded)
            self.assertNotIn("record_lead_disposition", encoded)
            self.assertNotIn("pane read", encoded)
            self.assertNotIn("agent read", encoded)


if __name__ == "__main__":
    unittest.main()
