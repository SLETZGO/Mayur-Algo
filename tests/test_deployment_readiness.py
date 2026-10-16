import unittest

from nifty_algo.services.deployment_readiness import (
    DEPLOYMENT_GATES,
    LIVE_GATES,
    DeploymentEvidence,
)


class DeploymentReadinessTests(unittest.TestCase):
    def test_empty_evidence_blocks_deployment_and_live(self):
        evidence = DeploymentEvidence()
        self.assertFalse(evidence.deployment.ready)
        self.assertEqual(evidence.deployment.missing, DEPLOYMENT_GATES)
        self.assertFalse(evidence.live_activation.ready)
        self.assertEqual(evidence.live_activation.missing, DEPLOYMENT_GATES + LIVE_GATES)

    def test_partial_evidence_reports_exact_missing_gates(self):
        evidence = DeploymentEvidence({DEPLOYMENT_GATES[0]: "broker-letter-123"})
        self.assertEqual(evidence.deployment.missing, DEPLOYMENT_GATES[1:])
        self.assertEqual(evidence.live_activation.missing, DEPLOYMENT_GATES[1:] + LIVE_GATES)

    def test_complete_references_report_readiness_without_arming_runtime(self):
        all_gates = DEPLOYMENT_GATES + LIVE_GATES
        evidence = DeploymentEvidence({gate: f"review:{gate}" for gate in all_gates})
        self.assertTrue(evidence.deployment.ready)
        self.assertTrue(evidence.live_activation.ready)
        # The report only summarizes supplied references; it has no config/order side effects.
        self.assertEqual(set(evidence.references), set(all_gates))

    def test_unknown_or_blank_evidence_is_rejected(self):
        with self.assertRaises(ValueError):
            DeploymentEvidence({"not_a_gate": "record"})
        with self.assertRaises(ValueError):
            DeploymentEvidence({DEPLOYMENT_GATES[0]: "   "})


if __name__ == "__main__":
    unittest.main()
