# CyberLab Agent v5.9.8.B
# awareness/knowledge_retriever.py
# Question-Driven Retrieval for Project Knowledge

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from lab_v4_dev.awareness.project_knowledge import (
    build_project_knowledge,
    ProjectKnowledgeModel,
    ConfidenceLevel,
)


class ProjectScope:
    """Deterministic scope labels used before current-project retrieval."""

    CURRENT_PROJECT = "CURRENT_PROJECT"
    EXTERNAL_PROJECT = "EXTERNAL_PROJECT"
    GENERIC_PROJECT = "GENERIC_PROJECT"
    HISTORICAL_PROJECT = "HISTORICAL_PROJECT"
    UNKNOWN = "UNKNOWN"


def resolve_project_scope(question: str) -> str:
    """Resolve whether a question authorizes current-project knowledge.

    This is deliberately local and conservative.  The word ``project`` by
    itself is not evidence that the user means CyberLab Agent.
    """
    q = str(question or "").strip().lower()
    if not q:
        return ProjectScope.UNKNOWN

    historical_markers = (
        "سابق", "سابقا", "سابقًا", "قديم", "النسخة القديمة", "نسخة قديمة",
        "ما الذي تغير", "تاريخ", "historical", "legacy", "archive", "archived",
    )
    external_markers = (
        "غير مشروعنا", "مشروع اخر", "مشروع آخر", "مشروع خارجي",
        "مشروع خارج", "خارج cyberlab", "المشروع الموجود عندي",
        "مشروع في الفضاء", "مشروع خارج الكرة", "مشروع وهمي", "مشروع عالمي",
        "external project", "another project", "outside cyberlab",
    )
    generic_markers = (
        "ما هو المشروع الجيد", "ما هو المشروع", "ما هي مراحل تطوير المشروع",
        "مراحل تطوير مشروع", "إدارة مشروع", "ادارة مشروع",
        "العمل على مشروع بشكل صحيح", "العمل على مشروع",
        "كيف تعمل على مشروع بشكل صحيح", "كيف أعمل على مشروع",
        "كيف اعمل على مشروع", "كيف يمكنك العمل على مشروع بشكل صحيح",
        "كيف تعمل على مشروع بشكل صحيح",
    )
    current_markers = (
        "cyberlab", "cyberlab-agent", "cyberlab agent", "مشروعنا",
        "مشروعك", "في مشروعك", "مشروعنا الحالي", "الوكيل",
        "conversationmanager", "conversation_manager", "intentparser",
        "intent_parser", "orchestrator", "eventloop", "event_loop", "run.py",
        "من أنت", "من انت", "هويتك", "بنيتك", "كيف تعالج رسالتي",
        "كيف تنتقل الطلبات داخل",
    )

    if any(marker in q for marker in historical_markers):
        return ProjectScope.HISTORICAL_PROJECT
    if any(marker in q for marker in external_markers):
        return ProjectScope.EXTERNAL_PROJECT
    if any(marker in q for marker in generic_markers):
        return ProjectScope.GENERIC_PROJECT
    if any(marker in q for marker in current_markers):
        return ProjectScope.CURRENT_PROJECT
    return ProjectScope.UNKNOWN


class QuestionClassifier:
    """Classify questions to determine retrieval strategy."""
    
    ARCHITECTURE_MARKERS = {
        "بنية", "معمارية", "هيكل", "طبقة", "طبقات", "مكون", "مكونات",
        "architecture", "layers", "structure", "components",
    }
    
    RELATIONSHIP_MARKERS = {
        "علاقة", "ارتباط", "يستدعي", "يستورد", "استيراد", "يرتبط",
        "related", "relationship", "call", "import", "depends",
    }
    
    EXECUTION_MARKERS = {
        "مسار", "تسلسل", "كيف", "تنتقل", "تنتقل", "رسالة", "تدفق",
        "flow", "path", "how", "sequence", "process", "execution",
    }
    
    FILE_MARKERS = {
        "ملف", "مجلد", "موقع", "path", "file", "directory", "location",
    }
    
    CAPABILITY_MARKERS = {
        "قدرات", "قادر", "يستطيع", "ممكن", "capabilities", "can", "able",
    }
    
    @classmethod
    def classify(cls, question: str) -> str:
        """Classify a question to determine retrieval approach."""
        q = question.lower()
        
        if any(m in q for m in cls.ARCHITECTURE_MARKERS):
            return "architecture"
        if any(m in q for m in cls.RELATIONSHIP_MARKERS):
            return "relationship"
        if any(m in q for m in cls.EXECUTION_MARKERS):
            return "execution"
        if any(m in q for m in cls.FILE_MARKERS):
            return "file"
        if any(m in q for m in cls.CAPABILITY_MARKERS):
            return "capability"
        
        return "general"


class KnowledgeRetriever:
    """Retrieve relevant project knowledge based on question."""
    
    def __init__(self, model: Optional[ProjectKnowledgeModel] = None):
        self.model = model or build_project_knowledge()
    
    def retrieve(self, question: str) -> Dict[str, Any]:
        """Main retrieval entry point."""
        scope = resolve_project_scope(question)
        if scope != ProjectScope.CURRENT_PROJECT:
            return self._scope_safe_result(scope)

        question_type = QuestionClassifier.classify(question)
        
        if question_type == "architecture":
            result = self._retrieve_architecture(question)
        elif question_type == "relationship":
            result = self._retrieve_relationship(question)
        elif question_type == "execution":
            result = self._retrieve_execution(question)
        elif question_type == "file":
            result = self._retrieve_file(question)
        elif question_type == "capability":
            result = self._retrieve_capability(question)
        else:
            result = self._retrieve_general(question)
        result["project_scope"] = scope
        result["current_project_knowledge"] = True
        return result

    @staticmethod
    def _scope_safe_result(scope: str) -> Dict[str, Any]:
        """Return scope evidence without exposing current-project metadata."""
        recommendation = {
            ProjectScope.EXTERNAL_PROJECT: (
                "تم تحديد مشروع خارجي؛ لا توجد بيانات مشروع خارجي محدد في هذا السياق."
            ),
            ProjectScope.GENERIC_PROJECT: (
                "السؤال عام عن المشاريع؛ أجب معرفة عامة دون استبداله بمشروع CyberLab."
            ),
            ProjectScope.HISTORICAL_PROJECT: (
                "السؤال تاريخي؛ لا تُعرض المعرفة الحالية ما لم يوجد استرجاع تاريخي صريح."
            ),
            ProjectScope.UNKNOWN: (
                "نطاق المشروع غير مؤكد؛ لا تفترض أن المقصود هو CyberLab."
            ),
        }[scope]
        return {
            "type": "scope_only",
            "project_scope": scope,
            "current_project_knowledge": False,
            "provenance": {
                "source": "local project-scope resolution",
                "confidence": ConfidenceLevel.STATIC_VERIFIED,
                "evidence": "deterministic lexical scope gate",
            },
            "recommendation": recommendation,
        }
    
    def _extract_identifiers(self, text: str) -> List[str]:
        """Extract potential component/file names from text."""
        identifiers = []
        
        # CamelCase or snake_case names
        words = re.findall(r'\b[a-zA-Z_]\w*\b', text)
        for word in words:
            if len(word) > 3:
                identifiers.append(word.lower())
        
        return identifiers
    
    def _retrieve_architecture(self, question: str) -> Dict[str, Any]:
        """Retrieve architecture-related knowledge."""
        return {
            "type": "architecture",
            "layers": list(self.model.layers.keys()),
            "layer_descriptions": self.model.layers,
            "entry_points": self.model.entry_points,
            "total_entities": len(self.model.entities),
            "provenance": {
                "source": "project knowledge model",
                "confidence": ConfidenceLevel.STATIC_VERIFIED,
                "evidence": "static source analysis",
            },
            "recommendation": (
                "استخدم معلومات الطبقات والمكونات للإجابة عن سؤال البنية المعمارية. "
                "لا تخترع طبقات غير موجودة."
            ),
        }
    
    def _retrieve_relationship(self, question: str) -> Dict[str, Any]:
        """Retrieve relationship-related knowledge."""
        identifiers = self._extract_identifiers(question)
        relationships = []
        
        for entity_id, entity in self.model.entities.items():
            for identifier in identifiers:
                if identifier in entity.path.lower() or identifier in entity.name.lower():
                    related = self.model.get_related_entities(entity_id)
                    relationships.append({
                        "entity": entity.path,
                        "related_to": [e.path for e in related],
                        "relationship_count": len(entity.relationships),
                    })
        
        return {
            "type": "relationship",
            "relationships_found": relationships,
            "total_relationships": len(self.model.relationships),
            "provenance": {
                "source": "project knowledge model",
                "confidence": ConfidenceLevel.STATIC_VERIFIED,
                "evidence": "import/call analysis",
            },
            "recommendation": (
                "استخدم العلاقات المستخرجة مباشرة من الكود. "
                "ميّز بين import و call و routing relationships."
            ),
        }
    
    def _retrieve_execution(self, question: str) -> Dict[str, Any]:
        """Retrieve execution flow knowledge."""
        execution_entities = []
        
        # Identify execution-related components
        key_patterns = [
            "conversation_manager",
            "intent_parser",
            "orchestrator",
            "event_loop",
            "executor",
        ]
        
        for entity in self.model.entities.values():
            if any(pattern in entity.path.lower() for pattern in key_patterns):
                execution_entities.append({
                    "path": entity.path,
                    "functions": entity.metadata.get("functions", [])[:5],
                    "imports": entity.metadata.get("imports", [])[:5],
                })
        
        return {
            "type": "execution",
            "execution_components": execution_entities,
            "entry_points": self.model.entry_points,
            "provenance": {
                "source": "project knowledge model",
                "confidence": ConfidenceLevel.STATIC_VERIFIED,
                "evidence": "component classification and relationship analysis",
            },
            "recommendation": (
                "استخدم مسارات المكونات وعلاقاتها لشرح سير تنفيذ الرسالة. "
                "لا تدّعِ runtime trace دون دليل."
            ),
        }
    
    def _retrieve_file(self, question: str) -> Dict[str, Any]:
        """Retrieve file/module-specific knowledge."""
        identifiers = self._extract_identifiers(question)
        matching_files = []
        
        for entity in self.model.entities.values():
            for identifier in identifiers:
                if identifier in entity.path.lower():
                    matching_files.append({
                        "path": entity.path,
                        "layer": entity.layer,
                        "functions": entity.metadata.get("functions", []),
                        "classes": entity.metadata.get("classes", []),
                        "imports": entity.metadata.get("imports", [])[:3],
                        "size": entity.metadata.get("size", 0),
                    })
                    break
        
        return {
            "type": "file",
            "matching_files": matching_files,
            "provenance": {
                "source": "project knowledge model",
                "confidence": ConfidenceLevel.STATIC_VERIFIED,
                "evidence": "static file analysis",
            },
            "recommendation": (
                "استخدم معلومات الملف المستخرجة من التحليل الثابت. "
                "لا تخترع دوال أو فئات غير موجودة فعلاً."
            ),
        }
    
    def _retrieve_capability(self, question: str) -> Dict[str, Any]:
        """Retrieve capability-related knowledge."""
        intent_files = [
            e for e in self.model.entities.values()
            if "intent" in e.path.lower()
        ]
        
        orchestrator_files = [
            e for e in self.model.entities.values()
            if "orchestrator" in e.path.lower()
        ]
        
        return {
            "type": "capability",
            "intent_handling": {
                "files": [e.path for e in intent_files],
                "functions": sum(
                    [e.metadata.get("functions", []) for e in intent_files],
                    []
                )[:10],
            },
            "execution_capability": {
                "files": [e.path for e in orchestrator_files],
                "functions": sum(
                    [e.metadata.get("functions", []) for e in orchestrator_files],
                    []
                )[:10],
            },
            "provenance": {
                "source": "project knowledge model",
                "confidence": ConfidenceLevel.STATIC_VERIFIED,
                "evidence": "component analysis",
            },
            "recommendation": (
                "استخدم المكونات والدوال المستخرجة فعلاً من الكود. "
                "لا تفترض قدرات غير مثبتة بالمصدر."
            ),
        }
    
    def _retrieve_general(self, question: str) -> Dict[str, Any]:
        """General retrieval for unclassified questions."""
        return {
            "type": "general",
            "total_files": len(self.model.entities),
            "layers": list(self.model.layers.keys()),
            "entry_points": self.model.entry_points,
            "provenance": {
                "source": "project knowledge model",
                "confidence": ConfidenceLevel.STATIC_VERIFIED,
                "evidence": "general project scan",
            },
            "recommendation": (
                "استخدم معلومات المشروع العامة للإجابة. "
                "أضف قيودًا عند عدم التأكد من تفاصيل محددة."
            ),
        }


def retrieve_for_question(question: str) -> Dict[str, Any]:
    """Convenience function for direct retrieval."""
    retriever = KnowledgeRetriever()
    return retriever.retrieve(question)
