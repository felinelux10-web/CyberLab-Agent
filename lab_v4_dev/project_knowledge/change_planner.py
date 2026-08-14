"""
PIE-004A — Change Planner

المسؤولية:
- بناء خطة أولية للتعديل.
- ترتيب خطوات العمل منطقياً.

لا يقوم بـ:
- تعديل الملفات.
- تنفيذ أي خطوة.
- تحليل AST.
"""

from .impact_analyzer import ChangeImpactAnalyzer as ImpactAnalyzer
from .impact_classifier import ImpactClassifier
from .impact_reasoner import ImpactReasoner
from .priority_planner import PriorityPlanner
from .execution_planner import ExecutionPlanner
from .execution_decision_engine import ExecutionDecisionEngine
from .execution_sequence_planner import ExecutionSequencePlanner
from .execution_validator import ExecutionValidator
from .execution_context import ExecutionContext
from .execution_scheduler import ExecutionScheduler
from .execution_report import ExecutionReport
from .execution_loop_manager import ExecutionLoopManager
from .execution_state_manager import ExecutionStateManager
from .execution_recovery_manager import ExecutionRecoveryManager
from .execution_simulation_engine import ExecutionSimulationEngine
from .simulation_decision_engine import SimulationDecisionEngine
from .execution_audit_logger import ExecutionAuditLogger
from .safe_execution_gate import SafeExecutionGate
from .execution_permission_manager import ExecutionPermissionManager
from .execution_transaction_manager import ExecutionTransactionManager
from .transaction_recovery_controller import TransactionRecoveryController
from .execution_result_collector import ExecutionResultCollector
from .final_execution_report import FinalExecutionReport



class ChangePlanner:

    
    def create_plan(self, changed_file):

        analyzer = ImpactAnalyzer()
        classifier = ImpactClassifier()
        reasoner = ImpactReasoner()
        priority = PriorityPlanner()

        impacted = analyzer.analyze_file_change(
            changed_file
        )

        classified = classifier.classify(
            impacted
        )

        explained = reasoner.explain(
            changed_file,
            classified
        )

        ranked = priority.rank(
            classified
        )

        execution = ExecutionPlanner().create_execution_plan(
            ranked
        )

        sequence = ExecutionSequencePlanner().build(
            execution
        )

        validation = ExecutionValidator().validate(
            sequence
        )

        context = ExecutionContext().create(
            sequence
        )

        next_step = ExecutionScheduler().next_step(
            context
        )

        simulation = ExecutionSimulationEngine().simulate(
            sequence
        )

        simulation_decision = SimulationDecisionEngine().decide(
            simulation
        )

        audit = ExecutionAuditLogger()

        audit.record(
            "simulation",
            simulation
        )

        audit.record(
            "simulation_decision",
            simulation_decision
        )

        execution_gate = SafeExecutionGate().check(
            simulation_decision
        )

        permission = ExecutionPermissionManager().check(
            execution_gate
        )

        transaction = ExecutionTransactionManager().start(
            next_step
        ) if permission.get("execute") else {
            "status": "not_started"
        }

        recovery_controller = TransactionRecoveryController()

        result_collector = ExecutionResultCollector()

        execution_result = result_collector.collect(
            transaction,
            {
                "status": "not_executed"
            }
        )

        decision = ExecutionDecisionEngine().decide(
            sequence
        )

        loop_state = ExecutionLoopManager().start(
            context
        )

        loop_state = ExecutionStateManager().advance(
            loop_state
        )

        recovery = {
            "status": "ready",
            "manager": "ExecutionRecoveryManager"
        }

        final_report = FinalExecutionReport().build(
            {
                "target": changed_file,
                "permission": permission,
                "transaction": transaction,
                "execution_result": execution_result,
                "recovery": recovery,
                "audit": audit.get_logs(),
            }
        )

        report = ExecutionReport().build(
            {
                "target": changed_file,
                "impacted": impacted,
                "priority": ranked,
                "decision": decision,
                "validation": validation,
                "next_step": next_step,
            "simulation": simulation,
            "simulation_decision": simulation_decision,
            "audit": audit.get_logs(),
            "execution_gate": execution_gate,
            "permission": permission,
            "transaction": transaction,
            "recovery_controller": recovery_controller,
            "execution_result": execution_result,
            }
        )

        return {
            "target": changed_file,
            "impacted": impacted,
            "classification": classified,
            "reasoning": explained,
            "priority": ranked,
            "execution_plan": execution,
            "execution_sequence": sequence,
            "validation": validation,
            "context": context,
            "loop_state": loop_state,
            "recovery": recovery,
            "next_step": next_step,
            "simulation": simulation,
            "simulation_decision": simulation_decision,
            "audit": audit.get_logs(),
            "execution_gate": execution_gate,
            "permission": permission,
            "transaction": transaction,
            "recovery_controller": recovery_controller,
            "execution_result": execution_result,
            "final_report": final_report,
            "report": report,
            "decision": decision,
        }
