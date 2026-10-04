# التقرير النهائي — توحيد دورة الحوار والمعرفة الذاتية

**المشروع:** CyberLab Agent  
**الفرع:** `work/BASELINE-01-intent-infrastructure`  
**Commit التنفيذ:** `5722285` — `fix: preserve grounded self-description completions`  
**التاريخ:** 2026-10-04  
**الحالة:** إصلاحات الحوار والمعرفة الذاتية مكتملة، والـcommit مدفوع إلى الفرع المطلوب. بقيت إخفاقات baseline مستقلة موثقة أدناه.

## 1. الخلاصة التنفيذية

اكتملت إصلاحات مسارات الحوار الذاتي للوكيل، وأضيفت معالجة للمشكلة التي ظهرت أثناء التحقق الحي: سؤال الهوية وصل إلى مسار self-knowledge، لكن GPT-5 mini أعاد HTTP 200 مع محتوى فارغ عندما استُنفد سقف completion عند 1600 رمزًا في الاستدلال. مع الإبقاء على السؤال وحقائق التأسيس كما هما ورفع السقف إلى 4000، أعاد النموذج ردًا ظاهرًا كاملًا وعرضه CLI.

أُثبتت أيضًا حماية على مستوى LLM Gateway: الاستجابة الفارغة لا تُعامل نجاحًا نهائيًا، بل تسمح بتجربة المزود التالي في سلسلة fallback. جرى تطبيق ميزانية أعلى **لأسئلة self-description الموثقة فقط**؛ المحادثة الاجتماعية العادية لا تحصل على self-knowledge وتبقى على ميزانيتها السابقة.

**التحقق:** 98 اختبارًا مستهدفًا ناجحًا. وفي المجموعة الكاملة القابلة للجمع (مع استثناء اختبار تكامل يطلب ملفًا مفقودًا بمسار مطلق)، نجح 355 اختبارًا وفشل 6؛ وهي الإخفاقات الستة نفسها التي ظهرت على commit الـbaseline النظيف، دون إضافة أي إخفاق جديد.

## 2. الحدود المعمارية التي حُفظت

المسار العام للرسالة:

```text
إدخال المستخدم
  → run.py
  → Agent.run()
  → ConversationManager.process()
  → ModeDetector / IntentParser
  → conversation semantics + context resolution
  → أحد مسارين:
      محادثة غير تنفيذية:
        Agent Self-Knowledge عند طلب وصف الوكيل
        → build_chat_prompt()
        → LLM Gateway
        → provider
      Intent تنفيذي:
        Orchestrator
        → PreparedExecutionRequest
        → EventLoop.submit_prepared()/tick()
        → Planner / PlanExecutionAdapter / Executor
```

ملكية الطبقات بقيت منفصلة كما طلب التقرير الأصلي:

- **ConversationManager:** تنسيق دورة الحوار وتحديد وجهة الرسالة.
- **DialogueMemory:** حالة الحوار والاستمرارية بين الأدوار.
- **ContextStore:** سياق التنفيذ، لا ذاكرة حوار بديلة.
- **Orchestrator:** مالك التنفيذ، لا يقرر المحادثة العامة ولا يحتوي قواعد «من أنت؟».
- **EventLoop:** يستقبل التنفيذ المُجهّز؛ لم يُضف إليه تحليل جديد للنص الخام.
- **LLM Gateway:** حدّ موحّد للمزودين وسلسلة fallback.
- **Agent Self-Knowledge:** حقائق مرتبطة بمصادر داخل الشفرة، لا تخمينات عن بنية نموذج LLM.

لم تُعدّل `run.py` أو `MASTER_REF` أو `lab_v4` المستقر أو ملفات الإصدارات التاريخية.

## 3. ما أُنجز

### 3.1 التوجيه الدلالي والوصف الذاتي

يُوجّه الوصف الذاتي إلى مسار المحادثة، لا إلى `Orchestrator`، عبر intents معيارية:

- `AGENT_IDENTITY`
- `AGENT_CAPABILITIES`
- `AGENT_ARCHITECTURE`
- `AGENT_EXECUTION_FLOW`
- `AGENT_LIMITS`

مصدر المعرفة الذاتية `lab_v4_dev/awareness/agent_self_knowledge.py` يزوّد prompt بحقائق مسندة إلى ملفات المشروع. لا يُستخدم ردّ ثابت لكل صياغة، ولا قائمة عبارات اجتماعية عامة. أُضيفت صيغة الهوية المختصرة **«من أنت؟»** إلى اختبارات الانحدار.

### 3.2 معالجة حد الرموز وطلب GPT-5

التشخيص الحي قارن الطلب نفسه مع prompt grounding ثابت حجمه **5512 محرفًا** وسؤال المستخدم حجمه **7 محارف**:

| الحالة | نتيجة المزود | نتيجة CLI |
|---|---|---|
| `max_completion_tokens=1600` | HTTP 200، `finish_reason=length`، 1600 completion token، `content=null` | لم يظهر جواب؛ مسار الفشل أعاد الرسالة الاحتياطية |
| `max_completion_tokens=4000` | HTTP 200، `finish_reason=stop`، 1947 completion token (منها 448 reasoning token)، نص 5080 محرفًا | ظهر الرد الكامل في CLI، بلا fallback |

الاستنتاج المحدود بالدليل: **المشكلة المرصودة كانت استنفاد سقف completion أثناء الاستدلال، لا انقطاع HTTP.** لم يتغير السؤال أو نص الحقائق بين المقارنة؛ لذا لا تدعم التجربة أن طول grounding نفسه هو سبب الفشل، وإن كان حمل السياق قد يزيد الحاجة إلى ميزانية كافية.

التعديل الدائم:

- تستخدم استدعاءات GPT-5 في OpenRouter `max_completion_tokens`، وتظل Gemini والنماذج الأخرى على `max_tokens`.
- يحصل self-description الموثق على ميزانية 4000؛ أما chat غير الذاتي فيبقى على 1600.
- لا يُمرر إعداد sampling `temperature` ضمن payload الخاص بعائلة GPT-5 في reasoning mode.
- أُضيف اختبار عقد يثبت اختلاف حقول الطلب المناسبة بين GPT-5 وGemini.

### 3.3 استجابة المزود الفارغة

قبل التعديل، كان بإمكان Gateway إعادة `LLMResponse` بحالة نجاح مع نص فارغ؛ وعندها لا تُجرّب سلسلة fallback. أصبح النص الفارغ/المكوّن من مسافات `EMPTY_PROVIDER_RESPONSE`، ويُعامل فشلًا قابلًا للتجاوز. يغطي اختبار جديد الانتقال من مزود أول فارغ إلى مزود ثانٍ ناجح.

### 3.4 إصلاح harness الاختبار الحي

كان harness المؤقت يحتوي أثر تتبع إضافيًا يقرأ `CYBERLAB_LIVE_TRACE` بعد استلام الرد. عدم ضبط هذا المتغير كان قادرًا على إحداث استثناء محلي بعد استجابة HTTP سليمة، وإظهار fallback زائف. ضُبط متغير التتبع في الاختبار النظيف وأُعيدت التجربة حتى ظهر الرد الكامل في CLI. ملفات التشخيص بقيت في مساحة `/tmp` ولم تُضمّن في المستودع.

## 4. نتائج التحقق

### الاختبارات المستهدفة

**98 passed** في مجموعة تغطي:

- self-description وgrounding وintents، بما فيها «من أنت؟».
- عدم تنفيذ سؤال الهوية عبر Orchestrator.
- بقاء الدردشة الاجتماعية بلا self-knowledge وبسقف 1600.
- التحولات الدلالية والسياقية G03/G06/G07 ومسارات intents.
- عقد GPT-5/Gemini ومعالجة provider الفارغ في Gateway.

### المجموعة الكاملة ومقارنة baseline

| التشغيل | النتيجة |
|---|---|
| المجموعة القابلة للجمع على baseline النظيف `4e78d2d`، مع استثناء الاختبار ذي المسار المفقود | 350 passed, 6 failed |
| المجموعة نفسها على الحالة الحالية قبل توثيق التقرير | 355 passed, 6 failed |
| الاختبارات المستهدفة الحالية | 98 passed |

قائمة الفشل الحالية مطابقة لقائمة baseline؛ لا يوجد `BASELINE_ONLY` أو `CURRENT_ONLY` في المقارنة.

### عائق جمع اختبار تكامل قديم

تشغيل `pytest` الكامل دون استثناء يتوقف أثناء collection في `tests/test_integration_knowledge.py` لأن الاختبار يفتح مسارًا مطلقًا غير موجود:

```text
/home/ubuntu/cyberlab_agent/project_data/roadmap.json
```

ظهر العائق نفسه على baseline النظيف. لم يُنشأ ملف بديل ولم يُغيّر الاختبار، لأنه يكتب مؤقتًا داخل ملف roadmap ويعيده في النهاية.

### إخفاقات baseline الستة (ليست ناتجة عن هذا التغيير)

1. `tests/test_p015_integration.py::test_end_to_end_status` — متوقع `success` والنتيجة `failed`؛ سجل الاختبار يظهر `system_status → failed`.
2. `tests/test_p02_prepared_event_loop.py::test_prepared_path_uses_planner_adapter_executor_without_raw_parser` — متوقع `executed` والنتيجة `blocked`.
3. `tests/test_p03_nlu_hardening.py::test_nlu_data_files_are_valid_json` — الملف `lab_v4_dev/nlu/language_patterns.json` غير موجود.
4. `tests/test_p05_architecture_contract.py::test_dialogue_contract_has_no_execution_symbols` — الملف `lab_v4_dev/conversation/dialogue_contract.py` غير موجود.
5. `tests/test_p10_planner.py::test_knowledge_router_can_bridge_legacy_change_plan_to_p10` — الاختبار يتوقع خطوتين (`count == 2`) والخطة الناتجة فيها خطوة واحدة.
6. `tests/test_p11_event_loop_execution.py::test_event_loop_executes_planned_shell_step` — متوقع `executed` والنتيجة `blocked`.

هذه البنود تحتاج معالجة مستقلة عن إصلاح الحوار؛ لم تُخفَ أو تُسجّل على أنها نجاح.

## 5. مصفوفة القبول

| المعيار | الحالة | الدليل/النطاق |
|---|---|---|
| إجابة الهوية grounded وعدم تقديم وصف LLM عام | ناجح | اختبار regression وCLI حي لسؤال «من أنت؟»؛ الرد يذكر ملفات المشروع ومساراته |
| intents القدرات/المعمارية/تدفق التنفيذ/الحدود | ناجح في اختبارات المسار | مجموعة self-description المستهدفة؛ لم يُجرَ live prompt منفصل لكل فئة في هذا التحقق النهائي |
| المحادثة الاجتماعية لا تتحول إلى self-description | ناجح | اختبار «مرحبًا» يثبت `max_tokens=1600` وغياب self-knowledge |
| فصل Project Architecture / Status / Cyber Explanation | ناجح في regression matrix | اختبارات intents المستهدفة |
| fallback عند النص الفارغ | ناجح | اختبار وحدة يثبت تجربة المزود التالي |
| عقد GPT-5/Gemini في OpenRouter | ناجح وحدويًا | حقول `max_completion_tokens` و`max_tokens` على التوالي |
| عقد EventLoop والتحضير | لم يُعدّل | لا ملفات EventLoop أو Planner تغيّرت؛ إخفاقات legacy ذات الصلة موجودة على baseline أيضًا |
| stable/master والإصدارات التاريخية | محفوظ | التعديلات محصورة في الفرع التجريبي المطلوب |

## 6. ملفات التغيير في commit التنفيذ

- `lab_v4_dev/conversation/conversation_manager.py` — رفع budget لطلبات self-knowledge فقط.
- `lab_v4_dev/llm/openrouter_provider.py` — بناء payload بحسب عقد عائلة النموذج.
- `lab_v4_dev/llm/gateway.py` — اعتبار الرد الفارغ فشلًا قابلًا للـfallback.
- `tests/test_agent_self_description.py` — صيغة «من أنت؟»، grounding، وحدود الميزانية.
- `tests/test_openrouter_token_semantics.py` — اختبارات عقد GPT-5/Gemini.
- `tests/test_gateway_empty_response.py` — اختبار fallback للرد الفارغ.

**التسليم الهيكلي:** [شجرة المشروع الكاملة](INTENT-INFRASTRUCTURE-PROJECT-TREE-2026-10-04.txt) — ملفات Git المتعقبة في الفرع مع مستندي التسليم، دون `.git` أو ملفات مؤقتة/متجاهلة.

## 7. الفرع والتسليم

- بقي العمل على `work/BASELINE-01-intent-infrastructure`.
- commit التنفيذ `5722285` مدفوع بنجاح إلى `origin/work/BASELINE-01-intent-infrastructure`.
- لم تُدمج التغييرات في stable/master.
- التوصية التالية: معالجة إخفاقات baseline الستة وملف roadmap المفقود في مهمة مستقلة، دون خلطها بإصلاح دورة الحوار.
